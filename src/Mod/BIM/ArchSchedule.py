# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2015 Yorik van Havre <yorik@uncreated.net>              *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

__title__ = "Arch Schedule"
__author__ = "Yorik van Havre"
__url__ = "https://www.freecad.org"

## @package ArchSchedule
#  \ingroup ARCH
#  \brief The Schedule object and tools
#
#  This module provides tools to build Schedule objects.
#  Schedules are objects that can count and gather information
#  about objects in the document, and fill a spreadsheet with the result

import FreeCAD

from draftutils import params

if FreeCAD.GuiUp:
    from PySide import QtCore, QtGui
    from PySide.QtCore import QT_TRANSLATE_NOOP
    import FreeCADGui
    from draftutils.translate import translate
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond


PARAMS = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/BIM")
VERBOSE = True # change this for silent recomputes


class _ArchScheduleDocObserver:

    "doc observer to monitor all recomputes"

    # https://forum.freecad.org/viewtopic.php?style=3&p=553377#p553377

    def __init__(self, doc, schedule):
        self.doc = doc
        self.schedule = schedule

    def slotRecomputedDocument(self, doc):
        if doc != self.doc:
            return
        try:
            self.schedule.Proxy.execute(self.schedule)
        except:
            pass


class _ArchSchedule:

    "the Arch Schedule object"

    def __init__(self,obj):

        self.setProperties(obj)
        obj.Proxy = self
        self.Type = "Schedule"

    def onDocumentRestored(self,obj):

        self.setProperties(obj)
        if hasattr(obj, "Result"):
            self.update_properties_0v21(obj)
        if hasattr(obj, "Description"):
            self.update_properties_1v1(obj)

    def update_properties_0v21(self,obj):
        from draftutils.messages import _wrn
        sp = obj.Result
        if sp is not None:
            self.setSchedulePropertySpreadsheet(sp, obj)
        obj.removeProperty("Result")
        _wrn("v0.21, " + obj.Label + ", " + translate("Arch", "removed property 'Result', and added property 'AutoUpdate'"))
        if sp is not None:
            _wrn("v0.21, " + sp.Label + ", " + translate("Arch", "added property 'Schedule'"))

    def update_properties_1v1(self,obj):
        from draftutils.messages import _wrn
        if obj.getTypeIdOfProperty("Description") == "App::PropertyStringList":
            obj.Operation = obj.Description
            obj.removeProperty("Description")
            _wrn("v1.1, " + obj.Label + ", " + translate("Arch", "renamed property 'Description' to 'Operation'"))
        for prop in ("Operation", "Value", "Unit", "Objects", "Filter", "CreateSpreadsheet", "DetailedResults"):
            obj.setGroupOfProperty(prop,"Schedule")

    def setProperties(self,obj):

        if not "Operation" in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList","Operation",         "Schedule",QT_TRANSLATE_NOOP("App::Property","The operation column"), locked=True)
        if not "Value" in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList","Value",             "Schedule",QT_TRANSLATE_NOOP("App::Property","The values column"), locked=True)
        if not "Unit" in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList","Unit",              "Schedule",QT_TRANSLATE_NOOP("App::Property","The units column"), locked=True)
        if not "Objects" in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList","Objects",           "Schedule",QT_TRANSLATE_NOOP("App::Property","The objects column"), locked=True)
        if not "Filter" in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList","Filter",            "Schedule",QT_TRANSLATE_NOOP("App::Property","The filter column"), locked=True)
        if not "CreateSpreadsheet" in obj.PropertiesList:
            obj.addProperty("App::PropertyBool",      "CreateSpreadsheet", "Schedule",QT_TRANSLATE_NOOP("App::Property","If True, a spreadsheet containing the results is recreated when needed"), locked=True)
        if not "DetailedResults" in obj.PropertiesList:
            obj.addProperty("App::PropertyBool",      "DetailedResults",   "Schedule",QT_TRANSLATE_NOOP("App::Property","If True, additional lines with each individual object are added to the results"), locked=True)
        if not "AutoUpdate" in obj.PropertiesList:
            obj.addProperty("App::PropertyBool",      "AutoUpdate",        "Schedule",QT_TRANSLATE_NOOP("App::Property","If True, the schedule and the associated spreadsheet are updated whenever the document is recomputed"), locked=True)
            obj.AutoUpdate = True

        # To add the doc observer:
        self.onChanged(obj,"AutoUpdate")

    def setSchedulePropertySpreadsheet(self, sp, obj):
        if not hasattr(sp, "Schedule"):
            sp.addProperty(
                "App::PropertyLink",
                "Schedule",
                "Arch",
                QT_TRANSLATE_NOOP("App::Property", "The BIM Schedule that uses this spreadsheet"),
                locked=True)
        sp.Schedule = obj

    def getSpreadSheet(self, obj, force=False):

        """Get the spreadsheet and store it in self.spreadsheet.

        If force is True the spreadsheet is created if required.
        """
        try: # Required as self.spreadsheet may get deleted.
            if getattr(self, "spreadsheet", None) is not None \
                    and getattr(self.spreadsheet, "Schedule", None) == obj:
                return self.spreadsheet
        except:
            pass
        else:
            for o in FreeCAD.ActiveDocument.Objects:
                if o.TypeId == "Spreadsheet::Sheet" \
                        and getattr(o, "Schedule", None) == obj:
                    self.spreadsheet = o
                    return self.spreadsheet
            if force:
                self.spreadsheet = FreeCAD.ActiveDocument.addObject("Spreadsheet::Sheet", "Result")
                self.setSchedulePropertySpreadsheet(self.spreadsheet, obj)
                return self.spreadsheet
            else:
                return None

    def onChanged(self,obj,prop):

        if prop == "CreateSpreadsheet":
            if obj.CreateSpreadsheet:
                self.getSpreadSheet(obj, force=True)
            else:
                sp = self.getSpreadSheet(obj)
                if sp is not None:
                    FreeCAD.ActiveDocument.removeObject(sp.Name)
                    self.spreadsheet = None
        elif prop == "AutoUpdate":
            if obj.AutoUpdate:
                if getattr(self, "docObserver", None) is None:
                    self.docObserver = _ArchScheduleDocObserver(FreeCAD.ActiveDocument, obj)
                    FreeCAD.addDocumentObserver(self.docObserver)
            elif getattr(self, "docObserver", None) is not None:
                FreeCAD.removeDocumentObserver(self.docObserver)
                self.docObserver = None

    def setSpreadsheetData(self,obj,force=False):

        """Fills a spreadsheet with the stored data"""

        if not hasattr(self,"data"):
            self.execute(obj)
        if not hasattr(self,"data"):
            return
        if not self.data:
            return
        if not (obj.CreateSpreadsheet or force):
            return
        sp = self.getSpreadSheet(obj, force=True)
        widths = [sp.getColumnWidth(col) for col in ("A", "B", "C")]
        sp.clearAll()
        # clearAll resets the column widths:
        for col, width in zip(("A", "B", "C"), widths):
            sp.setColumnWidth(col, width)
        # set headers
        sp.set("A1", "Operation")
        sp.set("B1", "Value")
        sp.set("C1", "Unit")
        sp.setStyle("A1:C1", "bold", "add")
        # write contents
        for k,v in self.data.items():
            sp.set(k,v)
        # recompute
        sp.recompute()
        sp.purgeTouched()   # Remove the confusing blue checkmark from the spreadsheet.
        for o in sp.InList: # Also recompute TechDraw views.
            o.TypeId == "TechDraw::DrawViewSpreadsheet"
            o.recompute()

    def execute(self,obj):

        # verify the data

        if not obj.Operation:
            # empty description column
            return
        for p in [obj.Value,obj.Unit,obj.Objects,obj.Filter]:
            # different number of items in each column
            if len(obj.Operation) != len(p):
                return

        self.data = {} # store all results in self.data, so it lives even without spreadsheet
        self.li = 1 # row index - starts at 2 to leave 2 blank rows for the title

        for i in range(len(obj.Operation)):
            self.li += 1
            if not obj.Operation[i]:
                # blank line
                continue
            # write description
            self.data["A"+str(self.li)] = obj.Operation[i]
            if VERBOSE:
                l= "OPERATION: "+obj.Operation[i]
                print("")
                print (l)
                print (len(l)*"=")

            # build set of valid objects

            objs = obj.Objects[i]
            val = obj.Value[i]
            unit = obj.Unit[i]
            details = obj.DetailedResults
            ifcfile = None
            elts = None
            if val:
                import Draft
                import Arch
                if objs:
                    objs = objs.split(";")
                    objs = [FreeCAD.ActiveDocument.getObject(o) for o in objs]
                    objs = [o for o in objs if o is not None]
                else:
                    if hasattr(getattr(FreeCAD.ActiveDocument, "Proxy", None), "ifcfile"):
                        ifcfile = FreeCAD.ActiveDocument.Proxy.ifcfile
                    objs = FreeCAD.ActiveDocument.Objects
                if len(objs) == 1:
                    if hasattr(objs[0], "StepId"):
                        from nativeifc import ifc_tools
                        ifcfile = ifc_tools.get_ifcfile(objs[0])
                    # remove object itself if the object is a group
                    if objs[0].isDerivedFrom("App::DocumentObjectGroup"):
                        objs = objs[0].Group
                objs = Draft.get_group_contents(objs)
                objs = self.expandArrays(objs)
                # Remove included objects (e.g. walls that are part of another wall,
                # base geometry, etc)
                objs = Arch.pruneIncluded(objs, strict=True, silent=True)
                # Remove all schedules and spreadsheets:
                objs = [o for o in objs if Draft.get_type(o) not in ["Schedule", "Spreadsheet::Sheet"]]

                # filter elements

                if obj.Filter[i]:
                    if ifcfile:
                        elts = self.get_ifc_elements(ifcfile, obj.Filter[i])
                    else:
                        objs = self.apply_filter(objs, obj.Filter[i])

                # perform operation: count or retrieve property

                if ifcfile:
                    if elts:
                        self.update_from_elts(elts, val, unit, details)
                elif objs:
                    self.update_from_objs(objs, val, unit, details)

        self.setSpreadsheetData(obj)
        self.save_ifc_props(obj)

    def apply_filter(self, objs, filters):
        """Applies the given filters to the given list of objects"""

        nobjs = []
        for o in objs:
            props = [p.upper() for p in o.PropertiesList]
            ok = True
            for f in filters.split(";"):
                args = [a.strip() for a in f.strip().split(":")]
                if args[0][0] == "!":
                    inv = True
                    prop = args[0][1:].upper()
                else:
                    inv = False
                    prop = args[0].upper()
                fval = args[1].upper()
                if prop == "TYPE":
                    prop = "IFCTYPE"
                if inv:
                    if prop in props:
                        csprop = o.PropertiesList[props.index(prop)]
                        if fval in getattr(o,csprop).upper():
                            ok = False
                else:
                    if not (prop in props):
                        ok = False
                    else:
                        csprop = o.PropertiesList[props.index(prop)]
                        if not (fval in getattr(o,csprop).upper()):
                            ok = False
            if ok:
                nobjs.append(o)
        return nobjs

    def get_ifc_elements(self, ifcfile, filters):
        """Retrieves IFC elements corresponding to the given filters"""

        elts = []
        for el in ifcfile.by_type("IfcProduct"):
            ok = True
            for f in filters.split(";"):
                args = [a.strip() for a in f.strip().split(":")]
                if args[0][0] == "!":
                    inv = True
                    prop = args[0][1:]
                else:
                    inv = False
                    prop = args[0]
                fval = args[1]
                if prop.upper() in ["CLASS", "IFCCLASS", "IFCTYPE"]:
                    prop = "is_a"
                if inv:
                    if prop == "is_a":
                        if not fval.upper().startswith("IFC"):
                            fval = "Ifc" + fval
                        fval = fval.replace(" ","")
                        if el.is_a(fval):
                            ok = False
                    else:
                        if prop in dir(el):
                            rval = getattr(el, prop)
                            if hasattr(rval, "id"):
                                if fval.startswith("#"):
                                    fval = int(fval[1:])
                            if rval == fval:
                                ok = False
                else:
                    if prop == "is_a":
                        if not fval.upper().startswith("IFC"):
                            fval = "Ifc" + fval
                        fval = fval.replace(" ","")
                        if not el.is_a(fval):
                            ok = False
                    else:
                        if prop in dir(el):
                            rval = getattr(el, prop)
                            if hasattr(rval, "id"):
                                if fval.startswith("#"):
                                    fval = int(fval[1:])
                            if rval != fval:
                                ok = False
                        else:
                            ok = False
            if ok:
                elts.append(el)
        return elts

    def update_from_objs(self, objs, val, unit, details):
        """Updates the spreadsheet data from FreeCAD objects"""

        if val.upper() == "COUNT":
            val = len(objs)
            if VERBOSE:
                print (val, ",".join([o.Label for o in objs]))
            self.data["B"+str(self.li)] = str(val)
            if details:
                # additional blank line...
                self.li += 1
                self.data["A"+str(self.li)] = " "
        else:
            vals = val.split(".")
            if vals[0][0].islower():
                # old-style: first member is not a property
                vals = vals[1:]
            sumval = 0

            # get unit
            tp = None
            unit = None
            q = None
            if unit:
                unit = unit.replace("^","")  # get rid of existing power symbol
                unit = unit.replace("2","^2")
                unit = unit.replace("3","^3")
                unit = unit.replace("²","^2")
                unit = unit.replace("³","^3")
                if "2" in unit:
                    tp = FreeCAD.Units.Area
                elif "3" in unit:
                    tp = FreeCAD.Units.Volume
                elif "deg" in unit:
                    tp = FreeCAD.Units.Angle
                else:
                    tp = FreeCAD.Units.Length

            # format value
            dv = params.get_param("Decimals",path="Units")
            fs = "{:."+str(dv)+"f}" # format string
            for o in objs:
                if VERBOSE:
                    l = o.Name+" ("+o.Label+"):"
                    print (l+(40-len(l))*" ",end="")
                try:
                    d = o
                    for v in vals:
                        d = getattr(d,v)
                    if hasattr(d,"Value"):
                        d = d.Value
                except Exception:
                    t = translate("Arch","Unable to retrieve value from object")
                    FreeCAD.Console.PrintWarning(t+": "+o.Name+"."+".".join(vals)+"\n")
                else:
                    if VERBOSE:
                        if tp and unit:
                            v = fs.format(FreeCAD.Units.Quantity(d,tp).getValueAs(unit).Value)
                            print(v,unit)
                        elif isinstance(d, str):
                            if d.replace('.', '', 1).isdigit():
                                print(fs.format(d))
                            else:
                                print(d)
                        else:
                            print(fs.format(d))
                    if details:
                        self.li += 1
                        self.data["A"+str(self.li)] = o.Name+" ("+o.Label+")"
                        if tp and unit:
                            q = FreeCAD.Units.Quantity(d,tp)
                            self.data["B"+str(self.li)] = str(q.getValueAs(unit).Value)
                            self.data["C"+str(self.li)] = unit
                        else:
                            self.data["B"+str(self.li)] = str(d)

                    if sumval:
                        sumval += d
                    else:
                        sumval = d
            val = sumval
            if tp:
                q = FreeCAD.Units.Quantity(val,tp)

            # write data
            if details:
                self.li += 1
                self.data["A"+str(self.li)] = "TOTAL"
            if q and unit:
                self.data["B"+str(self.li)] = str(q.getValueAs(unit).Value)
                self.data["C"+str(self.li)] = unit
            else:
                self.data["B"+str(self.li)] = str(val)
            if VERBOSE:
                if tp and unit:
                    v = fs.format(FreeCAD.Units.Quantity(val,tp).getValueAs(unit).Value)
                    print("TOTAL:"+34*" "+v+" "+unit)
                elif isinstance(val, str):
                    if val.replace('.', '', 1).isdigit():
                        v = fs.format(val)
                        print("TOTAL:"+34*" "+v)
                    else:
                        print("TOTAL:"+34*" "+val)
                else:
                    v = fs.format(val)
                    print("TOTAL:"+34*" "+v)

    def update_from_elts(self, elts, val, unit, details):
        """Updates the spreadsheet data from IFC elements"""

        if val.upper() == "COUNT":
            val = len(elts)
            if VERBOSE:
                print ("COUNT:", val, "(", ",".join(["#"+str(e.id()) for e in elts]), ")")
            self.data["B"+str(self.li)] = str(val)
            if details:
                # additional blank line...
                self.li += 1
                self.data["A"+str(self.li)] = " "
        else:
            total = 0
            for el in elts:
                if val in dir(el):
                    elval = getattr(el, val, "")
                    if isinstance(elval, tuple):
                        if len(elval) == 1:
                            elval = elval[0]
                        elif len(elval) == 0:
                            elval = ""
                    if hasattr(elval, "is_a") and elval.is_a("IfcRelationship"):
                        for att in dir(elval):
                            if att.startswith("Relating"):
                                targ = getattr(elval, att)
                                if targ != el:
                                    elval = targ
                                    break
                            elif att.startswith("Related"):
                                if not elval in getattr(elval, att):
                                    elval = str(getattr(elval, att))
                                    break
                    if details:
                        self.li += 1
                        name = el.Name if el.Name else ""
                        self.data["A"+str(self.li)] = "#" + str(el.id()) + name
                        self.data["B"+str(self.li)] = str(elval)
                        if VERBOSE:
                            print("#"+str(el.id())+"."+val+" = "+str(elval))
                    if isinstance(elval, str) and elval.replace('.', '', 1).isdigit():
                        total += float(elval)
                    elif isinstance(elval, (int, float)):
                        total += elval
            if total:
                if details:
                    self.li += 1
                    self.data["A"+str(self.li)] = "TOTAL"
                self.data["B"+str(self.li)] = str(total)
                if VERBOSE:
                    print("TOTAL:",str(total))

    def create_ifc(self, obj, ifcfile, export=False):
        """Creates an IFC element for this object"""

        from nativeifc import ifc_tools  # lazy loading

        proj = ifcfile.by_type("IfcProject")[0]
        elt = ifc_tools.api_run("root.create_entity", ifcfile, ifc_class="IfcControl")
        ifc_tools.set_attribute(ifcfile, elt, "Name", obj.Label)
        ifc_tools.api_run("project.assign_declaration", ifcfile, definitions=[elt], relating_context=proj)
        if not export:
            ifc_tools.add_properties(obj, ifcfile, elt)
        return elt

    def save_ifc_props(self, obj, ifcfile=None, elt=None):
        """Saves the object data to IFC"""

        from nativeifc import ifc_psets  # lazy loading

        ifc_psets.edit_pset(obj, "Operation", "::".join(obj.Operation), ifcfile=ifcfile, element=elt)
        ifc_psets.edit_pset(obj, "Value", "::".join(obj.Value), ifcfile=ifcfile, element=elt)
        ifc_psets.edit_pset(obj, "Unit", "::".join(obj.Unit), ifcfile=ifcfile, element=elt)
        ifc_psets.edit_pset(obj, "Objects", "::".join(obj.Objects), ifcfile=ifcfile, element=elt)
        ifc_psets.edit_pset(obj, "Filter", "::".join(obj.Filter), ifcfile=ifcfile, element=elt)

    def  export_ifc(self, obj, ifcfile):
        """Exports the object to IFC (does not modify the FreeCAD object)."""

        elt = self.create_ifc(obj, ifcfile, export=True)
        self.save_ifc_props(obj, ifcfile, elt)
        return elt

    def dumps(self):

        return self.Type

    def loads(self,state):

        if state:
            self.Type = state

    def getIfcClass(self, obj):
        """gets the IFC class of this object"""

        if hasattr(obj, "IfcType"):
            return obj.IfcType
        elif hasattr(obj, "IfcRole"):
            return obj.IfcRole
        elif hasattr(obj, "IfcClass"):
            return obj.IfcClass
        else:
            return None

    def getArray(self, obj):
        "returns a count number if this object needs to be duplicated"

        import Draft

        elementCount = 0

        # The given object can belong to multiple arrays
        # o is a potential parent array of the given object
        for o in obj.InList:
            if Draft.getType(o) == "Array":
                elementCount += o.Count

        return elementCount

    def expandArrays(self, objs):
        """Expands array elements in the given list of objects"""

        expandedobjs = []

        for obj in objs:
            ifcClass = self.getIfcClass(obj)
            # This filters out the array object itself, which has no IFC class,
            # but leaves the array elements, which do have an IFC class.
            if ifcClass:
                expandedobjs.append(obj)
                # If the object is in an array, add it and the rest of its elements
                # to the list.
                array = self.getArray(obj)
                for i in range(1, array): # The first element (0) was already added
                    expandedobjs.append(obj)

        return expandedobjs

class _ViewProviderArchSchedule:

    "A View Provider for Schedules"

    def __init__(self,vobj):
        vobj.Proxy = self

    def getIcon(self):
        if self.Object.AutoUpdate is False:
            import TechDrawGui
            return ":/icons/TechDraw_TreePageUnsync.svg"
        import Arch_rc
        return ":/icons/Arch_Schedule.svg"

    def isShow(self):
        return True

    def attach(self, vobj):
        self.Object = vobj.Object

    def setEdit(self, vobj, mode=0):
        if mode != 0:
            return None

        self.taskd = ArchScheduleTaskPanel(vobj.Object)
        if not self.taskd.form.isVisible():
            from PySide import QtCore
            QtCore.QTimer.singleShot(100, self.showEditor)
        return True

    def showEditor(self):

        if hasattr(self, "taskd"):
            self.taskd.form.show()

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None

        return True

    def doubleClicked(self, vobj):
        self.edit()

    def setupContextMenu(self, vobj, menu):

        if FreeCADGui.activeWorkbench().name() != 'BIMWorkbench':
            return

        actionEdit = QtGui.QAction(translate("Arch", "Edit"),
                                   menu)
        QtCore.QObject.connect(actionEdit,
                               QtCore.SIGNAL("triggered()"),
                               self.edit)
        menu.addAction(actionEdit)

        if self.Object.CreateSpreadsheet is True:
            msg = translate("Arch", "Remove spreadsheet")
        else:
            msg = translate("Arch", "Attach spreadsheet")
        actionToggleSpreadsheet = QtGui.QAction(QtGui.QIcon(":/icons/Arch_Schedule.svg"),
                                                msg,
                                                menu)
        QtCore.QObject.connect(actionToggleSpreadsheet,
                               QtCore.SIGNAL("triggered()"),
                               self.toggleSpreadsheet)
        menu.addAction(actionToggleSpreadsheet)

    def edit(self):
        FreeCADGui.ActiveDocument.setEdit(self.Object, 0)

    def toggleSpreadsheet(self):
        self.Object.CreateSpreadsheet = not self.Object.CreateSpreadsheet

    def claimChildren(self):
        if hasattr(self,"Object"):
            return [self.Object.Proxy.getSpreadSheet(self.Object)]

    def dumps(self):
        return None

    def loads(self,state):
        return None

    def getDisplayModes(self,vobj):
        return ["Default"]

    def getDefaultDisplayMode(self):
        return "Default"

    def setDisplayMode(self,mode):
        return mode


class ArchScheduleTaskPanel:

    '''The editmode TaskPanel for Schedules'''

    def __init__(self,obj=None):

        """Sets the panel up"""

        self.obj = obj
        self.form = FreeCADGui.PySideUic.loadUi(":/ui/ArchSchedule.ui")
        self.form.setWindowIcon(QtGui.QIcon(":/icons/Arch_Schedule.svg"))

        # set icons
        self.form.buttonAdd.setIcon(QtGui.QIcon(":/icons/list-add.svg"))
        self.form.buttonDel.setIcon(QtGui.QIcon(":/icons/list-remove.svg"))
        self.form.buttonClear.setIcon(QtGui.QIcon(":/icons/delete.svg"))
        self.form.buttonImport.setIcon(QtGui.QIcon(":/icons/document-open.svg"))
        self.form.buttonExport.setIcon(QtGui.QIcon(":/icons/document-save.svg"))
        self.form.buttonSelect.setIcon(QtGui.QIcon(":/icons/edit-select-all.svg"))

        # restore widths
        self.form.list.setColumnWidth(0,params.get_param_arch("ScheduleColumnWidth0"))
        self.form.list.setColumnWidth(1,params.get_param_arch("ScheduleColumnWidth1"))
        self.form.list.setColumnWidth(2,params.get_param_arch("ScheduleColumnWidth2"))
        self.form.list.setColumnWidth(3,params.get_param_arch("ScheduleColumnWidth3"))
        w = params.get_param_arch("ScheduleDialogWidth")
        h = params.get_param_arch("ScheduleDialogHeight")
        self.form.resize(w,h)

        # restore default states
        self.form.checkAutoUpdate.setChecked(PARAMS.GetBool("ScheduleAutoUpdate", False))

        # set delegate - Not using custom delegates for now...
        #self.form.list.setItemDelegate(ScheduleDelegate())
        #self.form.list.setEditTriggers(QtGui.QAbstractItemView.DoubleClicked)

        # connect slots
        self.form.buttonAdd.clicked.connect(self.add)
        self.form.buttonDel.clicked.connect(self.remove)
        self.form.buttonClear.clicked.connect(self.clear)
        self.form.buttonImport.clicked.connect(self.importCSV)
        self.form.buttonExport.clicked.connect(self.export)
        self.form.buttonSelect.clicked.connect(self.select)
        self.form.buttonBox.accepted.connect(self.accept)
        self.form.buttonBox.rejected.connect(self.reject)
        self.form.rejected.connect(self.reject)
        self.form.list.clearContents()

        if self.obj:
            #for p in [obj.Value,obj.Unit,obj.Objects,obj.Filter]:
            #    if len(obj.Operation) != len(p):
            #        return
            self.form.list.setRowCount(len(obj.Operation))
            for i in range(5):
                for j in range(len(obj.Operation)):
                    try:
                        text = [obj.Operation,obj.Value,obj.Unit,obj.Objects,obj.Filter][i][j]
                    except:
                        text = ""
                    item = QtGui.QTableWidgetItem(text)
                    self.form.list.setItem(j,i,item)
            self.form.lineEditName.setText(self.obj.Label)
            self.form.checkSpreadsheet.setChecked(self.obj.CreateSpreadsheet)
            self.form.checkDetailed.setChecked(self.obj.DetailedResults)
            self.form.checkAutoUpdate.setChecked(self.obj.AutoUpdate)

        # center over FreeCAD window
        mw = FreeCADGui.getMainWindow()
        self.form.move(mw.frameGeometry().topLeft() + mw.rect().center() - self.form.rect().center())

        self.form.show()

    def add(self):

        """Adds a new row below the last one"""

        self.form.list.insertRow(self.form.list.currentRow()+1)

    def remove(self):

        """Removes the current row"""

        if self.form.list.currentRow() >= 0:
            self.form.list.removeRow(self.form.list.currentRow())

    def clear(self):

        """Clears the list"""

        self.form.list.clearContents()
        self.form.list.setRowCount(0)

    def importCSV(self):

        """Imports a CSV file"""

        filename = QtGui.QFileDialog.getOpenFileName(QtGui.QApplication.activeWindow(), translate("Arch","Import CSV file"), None, "CSV files (*.csv *.CSV)")
        if filename:
            filename = filename[0]
            self.form.list.clearContents()
            import csv
            with open(filename,'r') as csvfile:
                r = 0
                for row in csv.reader(csvfile):
                    self.form.list.insertRow(r)
                    for i in range(5):
                        if len(row) > i:
                            t = row[i]
                            #t = t.replace("²","^2")
                            #t = t.replace("³","^3")
                            self.form.list.setItem(r,i,QtGui.QTableWidgetItem(t))
                    r += 1

    def export(self):

        """Exports the results as MD or CSV"""

        # commit latest changes
        self.writeValues()

        # tests
        if not("Up-to-date" in self.obj.State):
            self.obj.Proxy.execute(self.obj)
        if not hasattr(self.obj.Proxy,"data"):
            return
        if not self.obj.Proxy.data:
            return

        filename = QtGui.QFileDialog.getSaveFileName(QtGui.QApplication.activeWindow(),
                                                     translate("Arch","Export CSV file"),
                                                     None,
                                                     "Comma-separated values (*.csv);;TAB-separated values (*.tsv);;Markdown (*.md)");
        if filename:
            filt = filename[1]
            filename = filename[0]
            # add missing extension
            if (not filename.lower().endswith(".csv")) and (not filename.lower().endswith(".tsv")) and (not filename.lower().endswith(".md")):
                if "csv" in filt:
                    filename += ".csv"
                elif "tsv" in filt:
                    filename += ".tsv"
                else:
                    filename += ".md"
            if filename.lower().endswith(".csv"):
                self.exportCSV(filename,delimiter=",")
            elif filename.lower().endswith(".tsv"):
                self.exportCSV(filename,delimiter="\t")
            elif filename.lower().endswith(".md"):
                self.exportMD(filename)
            else:
                FreeCAD.Console.PrintError(translate("Arch","Unable to recognize that file type")+":"+filename+"\n")

    def getRows(self):

        """get the rows that contain data"""

        rows = []
        if hasattr(self.obj.Proxy,"data") and self.obj.Proxy.data:
            for key in self.obj.Proxy.data.keys():
                n = key[1:]
                if not n in rows:
                    rows.append(n)
        rows.sort(key=int)
        return rows

    def exportCSV(self,filename,delimiter="\t"):

        """Exports the results as a CSV/TSV file"""

        import csv
        with open(filename, 'w') as csvfile:
            csvfile = csv.writer(csvfile,delimiter=delimiter)
            csvfile.writerow([translate("Arch","Operation"),translate("Arch","Value"),translate("Arch","Unit")])
            if self.obj.DetailedResults:
                csvfile.writerow(["","",""])
            for i in self.getRows():
                r = []
                for j in ["A","B","C"]:
                    if j+i in self.obj.Proxy.data:
                        r.append(str(self.obj.Proxy.data[j+i]))
                    else:
                        r.append("")
                csvfile.writerow(r)
        print("successfully exported ",filename)

    def exportMD(self,filename):

        """Exports the results as a Markdown file"""

        with open(filename, 'w') as mdfile:
            mdfile.write("| "+translate("Arch","Operation")+" | "+translate("Arch","Value")+" | "+translate("Arch","Unit")+" |\n")
            mdfile.write("| --- | --- | --- |\n")
            if self.obj.DetailedResults:
                mdfile.write("| | | |\n")
            for i in self.getRows():
                r = []
                for j in ["A","B","C"]:
                    if j+i in self.obj.Proxy.data:
                        r.append(str(self.obj.Proxy.data[j+i]))
                    else:
                        r.append("")
                mdfile.write("| "+" | ".join(r)+" |\n")
        print("successfully exported ",filename)

    def select(self):

        """Adds selected objects to current row"""

        if self.form.list.currentRow() >= 0:
            sel = ""
            for o in FreeCADGui.Selection.getSelection():
                if o != self.obj:
                    if sel:
                        sel += ";"
                    sel += o.Name
            if sel:
                self.form.list.setItem(self.form.list.currentRow(),3,QtGui.QTableWidgetItem(sel))

    def accept(self):

        """Saves the changes and closes the dialog"""

        # store widths
        params.set_param_arch("ScheduleColumnWidth0",self.form.list.columnWidth(0))
        params.set_param_arch("ScheduleColumnWidth1",self.form.list.columnWidth(1))
        params.set_param_arch("ScheduleColumnWidth2",self.form.list.columnWidth(2))
        params.set_param_arch("ScheduleColumnWidth3",self.form.list.columnWidth(3))
        params.set_param_arch("ScheduleDialogWidth",self.form.width())
        params.set_param_arch("ScheduleDialogHeight",self.form.height())

        # store default states
        PARAMS.SetBool("ScheduleAutoUpdate", self.form.checkAutoUpdate.isChecked())

        # commit values
        self.writeValues()
        self.form.hide()
        FreeCADGui.ActiveDocument.resetEdit()
        return True

    def reject(self):

        """Close dialog without saving"""

        self.form.hide()
        FreeCADGui.ActiveDocument.resetEdit()
        return True

    def writeValues(self):

        """commits values and recalculate"""

        if not self.obj:
            import Arch
            self.obj = Arch.makeSchedule()
        lists = [ [], [], [], [], [] ]
        for i in range(self.form.list.rowCount()):
            for j in range(5):
                cell = self.form.list.item(i,j)
                if cell:
                    lists[j].append(cell.text())
                else:
                    lists[j].append("")
        FreeCAD.ActiveDocument.openTransaction("Edited Schedule")
        self.obj.Operation = lists[0]
        self.obj.Value = lists[1]
        self.obj.Unit = lists[2]
        self.obj.Objects = lists[3]
        self.obj.Filter = lists[4]
        self.obj.Label = self.form.lineEditName.text()
        self.obj.DetailedResults = self.form.checkDetailed.isChecked()
        self.obj.CreateSpreadsheet = self.form.checkSpreadsheet.isChecked()
        self.obj.AutoUpdate = self.form.checkAutoUpdate.isChecked()
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
