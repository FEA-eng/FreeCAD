/***************************************************************************
 *   Copyright (c) 2014 Werner Mayer <wmayer[at]users.sourceforge.net>     *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/

#include "PreCompiled.h"

#ifndef _PreComp_
# include <QApplication>
# include <QFile>
# include <QGraphicsScene>
# include <QGraphicsSvgItem>
# include <QGraphicsView>
# include <QMessageBox>
# include <QMouseEvent>
# include <QPrinter>
# include <QPrintDialog>
# include <QPrintPreviewDialog>
# include <QProcess>
# include <QSvgRenderer>
# include <QScrollBar>
# include <QThread>
#endif

#include <App/Application.h>
#include <App/Document.h>

#include "GraphvizView.h"
#include "GraphicsViewZoom.h"
#include "FileDialog.h"
#include "MainWindow.h"


using namespace Gui;
namespace sp = std::placeholders;

namespace Gui {

/**
 * @brief The GraphvizWorker class
 *
 * Implements a QThread class that does the actual conversion from dot to
 * svg. All critical communication is done using queued signals.
 *
 */

class GraphvizWorker : public QThread {
    Q_OBJECT
public:
    explicit GraphvizWorker(QObject * parent = nullptr)
        : QThread(parent)
    {
    }

    ~GraphvizWorker() override
    {
        dotProc.moveToThread(this);
        unflattenProc.moveToThread(this);
    }

    void setData(const QByteArray & data)
    {
        str = data;
    }

    void startThread() {
        // This doesn't actually run a thread but calls the function
        // directly in the main thread.
        // This is needed because embedding a QProcess into a QThread
        // causes some problems with Qt5.
        run();
        // Can't use the finished() signal of QThread
        Q_EMIT emitFinished();
    }

    void run() override {
        QByteArray preprocessed = str;

        ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/DependencyGraph");
        if(hGrp->GetBool("Unflatten", true)) {
            // Write data to unflatten process
            unflattenProc.write(str);
            unflattenProc.closeWriteChannel();
            //no error handling: unflatten is optional
            unflattenProc.waitForFinished();
                preprocessed = unflattenProc.readAll();
        } else {
            unflattenProc.closeWriteChannel();
            unflattenProc.waitForFinished();
        }

        dotProc.write(preprocessed);
        dotProc.closeWriteChannel();
        if (!dotProc.waitForFinished()) {
            Q_EMIT error();
            quit();
        }

        // Emit result; it will get queued for processing in the main thread
        Q_EMIT svgFileRead(dotProc.readAll());
    }

    QProcess * dotProcess() {
        return &dotProc;
    }

    QProcess * unflattenProcess() {
        return &unflattenProc;
    }

Q_SIGNALS:
    void svgFileRead(const QByteArray & data);
    void error();
    void emitFinished();

private:
    QProcess dotProc, unflattenProc;
    QByteArray str, flatStr;
};

// Simple wrapper around QGraphicsView to make panning possible
class GraphvizGraphicsView final : public QGraphicsView
{
  public:
    GraphvizGraphicsView(QGraphicsScene* scene, QWidget* parent);
    ~GraphvizGraphicsView() override = default;

    GraphvizGraphicsView(const GraphvizGraphicsView&) = delete;
    GraphvizGraphicsView(GraphvizGraphicsView&&) = delete;
    GraphvizGraphicsView& operator=(const GraphvizGraphicsView&) = delete;
    GraphvizGraphicsView& operator=(GraphvizGraphicsView&&) = delete;

  protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;

  private:
    bool   isPanning{false};
    QPoint panStart;
};

GraphvizGraphicsView::GraphvizGraphicsView(QGraphicsScene* scene, QWidget* parent) : QGraphicsView(scene, parent)
{
}

void GraphvizGraphicsView::mousePressEvent(QMouseEvent* e)
{
  if (e && e->button() == Qt::LeftButton) {
    isPanning = true;
    panStart = e->pos();
    e->accept();
    QApplication::setOverrideCursor(Qt::ClosedHandCursor);
  }

  QGraphicsView::mousePressEvent(e);

  return;
}

void GraphvizGraphicsView::mouseMoveEvent(QMouseEvent *e)
{
  if (!e)
    return;

  if (isPanning) {
    auto *horizontalScrollbar = horizontalScrollBar();
    auto *verticalScrollbar = verticalScrollBar();
    if (!horizontalScrollbar || !verticalScrollbar)
      return;

    auto direction = e->pos() - panStart;
    horizontalScrollbar->setValue(horizontalScrollbar->value() - direction.x());
    verticalScrollbar->setValue(verticalScrollbar->value() - direction.y());

    panStart = e->pos();
    e->accept();
  }

  QGraphicsView::mouseMoveEvent(e);

  return;
}

void GraphvizGraphicsView::mouseReleaseEvent(QMouseEvent* e)
{
  if(e && e->button() & Qt::LeftButton)
  {
    isPanning = false;
    QApplication::restoreOverrideCursor();
    e->accept();
  }

  QGraphicsView::mouseReleaseEvent(e);

  return;
}

}

/* TRANSLATOR Gui::GraphvizView */

GraphvizView::GraphvizView(App::Document & _doc, QWidget* parent)
  : MDIView(nullptr, parent)
  , doc(_doc)
  , nPending(0)
{
    // Create scene
    scene = new QGraphicsScene();

    // Create item to hold the graph
    svgItem = new QGraphicsSvgItem();
    renderer = new QSvgRenderer(this);
    svgItem->setSharedRenderer(renderer);
    scene->addItem(svgItem);

    // Create view and zoomer object
    view = new GraphvizGraphicsView(scene, this);
    zoomer = new GraphicsViewZoom(view);
    zoomer->set_modifiers(Qt::NoModifier);
    view->show();

    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath
            ("User parameter:BaseApp/Preferences/View");
    bool on = hGrp->GetBool("InvertZoom", true);
    zoomer->set_zoom_inverted(on);

    // Set central widget to view
    setCentralWidget(view);

    // Create worker thread
    thread = new GraphvizWorker(this);
    connect(thread, &GraphvizWorker::emitFinished, this, &GraphvizView::done);
    connect(thread, &GraphvizWorker::finished, this, &GraphvizView::done);
    connect(thread, &GraphvizWorker::error, this, &GraphvizView::error);
    connect(thread, &GraphvizWorker::svgFileRead, this, &GraphvizView::svgFileRead);

    //NOLINTBEGIN
    // Connect signal from document
    recomputeConnection = _doc.signalRecomputed.connect(std::bind(&GraphvizView::updateSvgItem, this, sp::_1));
    undoConnection = _doc.signalUndo.connect(std::bind(&GraphvizView::updateSvgItem, this, sp::_1));
    redoConnection = _doc.signalRedo.connect(std::bind(&GraphvizView::updateSvgItem, this, sp::_1));
    //NOLINTEND

    updateSvgItem(_doc);
}

GraphvizView::~GraphvizView()
{
    delete scene;
    delete view;
}

void GraphvizView::updateSvgItem(const App::Document &doc)
{
    nPending++;

    // Skip if thread is working now
    if (nPending > 1)
        return;

    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/Paths");
    QProcess * dotProc = thread->dotProcess();
    QProcess * flatProc = thread->unflattenProcess();
    QStringList args, flatArgs;
    // TODO: Make -Granksep flag value variable depending on number of edges,
    // the downside is that the value affects all subgraphs
    args << QLatin1String("-Granksep=2") << QLatin1String("-Goutputorder=edgesfirst")
         << QLatin1String("-Gsplines=ortho") << QLatin1String("-Tsvg");
    flatArgs << QLatin1String("-c2 -l2");
    auto dot = QStringLiteral("dot");
    auto unflatten = QStringLiteral("unflatten");
    auto path = QString::fromUtf8(hGrp->GetASCII("Graphviz").c_str());
    bool pathChanged = false;
    QDir dir;
    if (!path.isEmpty()) {
        dir = QDir(path);
        dot = dir.filePath(QStringLiteral("dot"));
        unflatten = dir.filePath(QStringLiteral("unflatten"));
    }
    dotProc->setEnvironment(QProcess::systemEnvironment());
    flatProc->setEnvironment(QProcess::systemEnvironment());
    do {
        flatProc->start(unflatten, flatArgs);
        bool value = flatProc->waitForStarted();
        Q_UNUSED(value); // quieten code analyzer
        dotProc->start(dot, args);
        if (!dotProc->waitForStarted()) {
            int ret = QMessageBox::warning(Gui::getMainWindow(),
                                           tr("Graphviz not found"),
                                           QStringLiteral("<html><head/><body>%1 "
                                                               "<a href=\"https://www.freecad.org/wiki/Std_DependencyGraph\">%2"
                                                               "</a><p>%3</p></body></html>")
                                           .arg(tr("Graphviz couldn't be found on your system."),
                                                tr("Read more about it here."),
                                                tr("Do you want to specify its installation path if it's already installed?")),
                                           QMessageBox::Yes, QMessageBox::No);
            if (ret == QMessageBox::No) {
                disconnectSignals();
                return;
            }
            path = QFileDialog::getExistingDirectory(Gui::getMainWindow(),
                                                     tr("Graphviz installation path"));
            if (path.isEmpty()) {
                disconnectSignals();
                return;
            }
            else {
                dir = QDir(path);
                dot = dir.filePath(QStringLiteral("dot"));
                unflatten = dir.filePath(QStringLiteral("unflatten"));
                pathChanged = true;
            }
        }
        else {
            if (pathChanged)
                hGrp->SetASCII("Graphviz", (const char*)path.toUtf8());
            break;
        }
    }
    while(true);

    // Create graph in dot format
    std::stringstream stream;
    doc.exportGraphviz(stream);
    graphCode = stream.str();

    // Update worker thread, and start it
    thread->setData(QByteArray(graphCode.c_str(), graphCode.size()));
    thread->startThread();
}

void GraphvizView::svgFileRead(const QByteArray & data)
{
    // Update renderer with new SVG file, and give message if something went wrong
    if (renderer->load(data))
        svgItem->setSharedRenderer(renderer);
    else {
        QMessageBox::warning(getMainWindow(),
                             tr("Graphviz failed"),
                             tr("Graphviz failed to create an image file"));
        disconnectSignals();
    }
}

void GraphvizView::error()
{
    // If the worker fails for some reason, stop giving it more data later
    disconnectSignals();
}

void GraphvizView::done()
{
    nPending--;
    if (nPending > 0) {
        nPending = 0;
        updateSvgItem(doc);
        thread->startThread();
    }
}

void GraphvizView::disconnectSignals()
{
    recomputeConnection.disconnect();
    undoConnection.disconnect();
    redoConnection.disconnect();
}

#include <QObject>
#include <QGraphicsView>

QByteArray GraphvizView::exportGraph(const QString& format)
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/Paths");
    QProcess dotProc, flatProc;
    QStringList args, flatArgs;
    args << QStringLiteral("-T%1").arg(format);
    flatArgs << QLatin1String("-c2 -l2");

#ifdef FC_OS_LINUX
    QString path = QString::fromUtf8(hGrp->GetASCII("Graphviz", "/usr/bin").c_str());
#else
    QString path = QString::fromUtf8(hGrp->GetASCII("Graphviz").c_str());
#endif

#ifdef FC_OS_WIN32
    QString exe = QStringLiteral("\"%1/dot\"").arg(path);
    QString unflatten = QStringLiteral("\"%1/unflatten\"").arg(path);
#else
    QString exe = QStringLiteral("%1/dot").arg(path);
    QString unflatten = QStringLiteral("%1/unflatten").arg(path);
#endif

    dotProc.setEnvironment(QProcess::systemEnvironment());
    dotProc.start(exe, args);
    if (!dotProc.waitForStarted()) {
        return {};
    }

    ParameterGrp::handle depGrp = App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/DependencyGraph");
    if(depGrp->GetBool("Unflatten", true)) {
        flatProc.setEnvironment(QProcess::systemEnvironment());
        flatProc.start(unflatten, flatArgs);
        if (!flatProc.waitForStarted()) {
            return {};
        }
        flatProc.write(graphCode.c_str(), graphCode.size());
        flatProc.closeWriteChannel();
        if (!flatProc.waitForFinished())
            return {};

        dotProc.write(flatProc.readAll());
    }
    else
        dotProc.write(graphCode.c_str(), graphCode.size());

    dotProc.closeWriteChannel();
    if (!dotProc.waitForFinished())
        return {};

    return dotProc.readAll();
}

bool GraphvizView::onMsg(const char* pMsg, const char**)
{
    if (strcmp("Save",pMsg) == 0 || strcmp("SaveAs",pMsg) == 0) {
        QList< QPair<QString, QString> > formatMap;
        formatMap << qMakePair(QStringLiteral("%1 (*.gv)").arg(tr("Graphviz format")), QStringLiteral("gv"));
        formatMap << qMakePair(QStringLiteral("%1 (*.png)").arg(tr("PNG format")), QStringLiteral("png"));
        formatMap << qMakePair(QStringLiteral("%1 (*.bmp)").arg(tr("Bitmap format")), QStringLiteral("bmp"));
        formatMap << qMakePair(QStringLiteral("%1 (*.gif)").arg(tr("GIF format")), QStringLiteral("gif"));
        formatMap << qMakePair(QStringLiteral("%1 (*.jpg)").arg(tr("JPG format")), QStringLiteral("jpg"));
        formatMap << qMakePair(QStringLiteral("%1 (*.svg)").arg(tr("SVG format")), QStringLiteral("svg"));
        formatMap << qMakePair(QStringLiteral("%1 (*.pdf)").arg(tr("PDF format")), QStringLiteral("pdf"));

        QStringList filter;
        for (const auto & it : std::as_const(formatMap)) {
            filter << it.first;
        }

        QString selectedFilter;
        QString fn = Gui::FileDialog::getSaveFileName(this, tr("Export graph"), QString(), filter.join(QLatin1String(";;")), &selectedFilter);
        if (!fn.isEmpty()) {
            QString format;
            for (const auto & it : std::as_const(formatMap)) {
                if (selectedFilter == it.first) {
                    format = it.second;
                    break;
                }
            }
            QByteArray buffer;
            if (format == QLatin1String("gv")) {
                std::stringstream str;
                doc.exportGraphviz(str);
                buffer = QByteArray::fromStdString(str.str());
            }
            else {
                buffer = exportGraph(format);
            }
            if (buffer.isEmpty()) {
                return true;
            }
            QFile file(fn);
            if (file.open(QFile::WriteOnly)) {
                file.write(buffer);
                file.close();
            }
        }
        return true;
    }
    else if (strcmp("Print",pMsg) == 0) {
        print();
        return true;
    }
    else if (strcmp("PrintPreview",pMsg) == 0) {
        printPreview();
        return true;
    }
    else if (strcmp("PrintPdf",pMsg) == 0) {
        printPdf();
        return true;
    }

    return false;
}

bool GraphvizView::onHasMsg(const char* pMsg) const
{
    if (strcmp("Save",pMsg) == 0)
        return true;
    else if (strcmp("SaveAs",pMsg) == 0)
        return true;
    else if (strcmp("Print",pMsg) == 0)
        return true;
    else if (strcmp("PrintPreview",pMsg) == 0)
        return true;
    else if (strcmp("PrintPdf",pMsg) == 0)
        return true;
    else if (strcmp("AllowsOverlayOnHover", pMsg) == 0)
        return true;
    return false;
}

void GraphvizView::print(QPrinter* printer)
{
    QPainter p(printer);
    QRect rect = printer->pageLayout().paintRectPixels(printer->resolution());
    view->scene()->render(&p, rect);
    //QByteArray buffer = exportGraph(QStringLiteral("svg"));
    //QSvgRenderer svg(buffer);
    //svg.render(&p, rect);
    p.end();
}

void GraphvizView::print()
{
    QPrinter printer(QPrinter::HighResolution);
    printer.setFullPage(true);
    printer.setPageOrientation(QPageLayout::Landscape);
    QPrintDialog dlg(&printer, this);
    if (dlg.exec() == QDialog::Accepted) {
        print(&printer);
    }
}

void GraphvizView::printPdf()
{
    QStringList filter;
    filter << QStringLiteral("%1 (*.pdf)").arg(tr("PDF format"));

    QString selectedFilter;
    QString fn = Gui::FileDialog::getSaveFileName(this, tr("Export graph"), QString(), filter.join(QLatin1String(";;")), &selectedFilter);
    if (!fn.isEmpty()) {
        QByteArray buffer = exportGraph(selectedFilter);
        if (buffer.isEmpty())
            return;
        QFile file(fn);
        if (file.open(QFile::WriteOnly)) {
            file.write(buffer);
            file.close();
        }
    }
}

void GraphvizView::printPreview()
{
    QPrinter printer(QPrinter::HighResolution);
    printer.setFullPage(true);
    printer.setPageOrientation(QPageLayout::Landscape);

    QPrintPreviewDialog dlg(&printer, this);
    connect(&dlg, &QPrintPreviewDialog::paintRequested,
            this, qOverload<QPrinter*>(&GraphvizView::print));
    dlg.exec();
}

#include "moc_GraphvizView.cpp"
#include "moc_GraphvizView-internal.cpp"
