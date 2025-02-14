#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  screw_maker2_0.py
#


"""
Macro to generate screws with FreeCAD.
Version 1.4 from 1st of September 2013
Version 1.5 from 23rd of December 2013
Corrected hex-heads above M12 not done.
Version 1.6 from 15th of March 2014
Added PySide support

Version 1.7 from April 2014
fixed bool type error. (int is not anymore accepted at linux)
fixed starting point of real thread at some screw types.

Version 1.8 from July 2014
first approach for a faster real thread

Version 1.9 / 2.0 July 2015
new calculation of starting point of thread
shell-based approach for screw generation
added:
ISO 14582 Hexalobular socket countersunk head screws, high head
ISO 14584 Hexalobular socket raised countersunk head screws
ISO 7380-2 Hexagon socket button head screws with collar
DIN 967 Cross recessed pan head screws with collar
ISO 4032 Hexagon nuts, Style 1
ISO 4033 Hexagon nuts, Style 2
ISO 4035 Hexagon thin nuts, chamfered
EN 1661 Hexagon nuts with flange
ISO 7094 definitions  Plain washers - Extra large series
ISO 7092 definitions  Plain washers - Small series
ISO 7093-1 Plain washer - Large series
Screw-tap to drill inner threads in parts with user defined length

ScrewMaker can now also used as a python module.
The following shows how to generate a screw from a python script:
  import screw_maker2_0

  threadDef = 'M3.5'
  o = screw_maker2_0.Screw()
  t = screw_maker2_0.Screw.setThreadType(o,'real')
  # Creates a Document-Object with label describing the screw
  d = screw_maker2_0.Screw.createScrew(o, 'ISO1207', threadDef, '20', 'real')

  # creates a shape in memory
  t = screw_maker2_0.Screw.setThreadType(o,'real')
  s = screw_maker1_9d.Screw.makeCountersunkHeadScrew(o, 'ISO14582', threadDef, 40.0)
  Part.show(s)



to do: check ISO7380 usage of rs and rt, actual only rs is used
check chamfer angle on hexogon heads and nuts
***************************************************************************
*   Copyright (c) 2013, 2014, 2015                                        *
*   Ulrich Brammer <ulrich1a[at]users.sourceforge.net>                    *
*   Refactor by shai 2022                                                 *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.      *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)    *
*   as published by the Free Software Foundation; either version 2 of     *
*   the License, or (at your option) any later version.                   *
*   for detail see the LICENCE text file.                                 *
*                                                                         *
*   This software is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
*   GNU Library General Public License for more details.                  *
*                                                                         *
*   You should have received a copy of the GNU Library General Public     *
*   License along with this macro; if not, write to the Free Software     *
*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
*   USA                                                                   *
*                                                                         *
***************************************************************************
"""

__author__ = "Ulrich Brammer <ulrich1a@users.sourceforge.net>"



import errno
import FreeCAD, Part, math, os
from FreeCAD import Base
import DraftVecUtils
import importlib
import FastenerBase
from FastenerBase import FsData

#from FastenersCmd import FastenerAttribs

#import FSmakeCountersunkHeadScrew
#from FSmakeCountersunkHeadScrew import *

DEBUG = False # set to True to show debug messages; does not work, still todo.

# some common constants
sqrt3 = math.sqrt(3)
cos30 = math.cos(math.radians(30))

class Screw:
    def __init__(self):
        self.objAvailable = True
        self.Tuner = 510
        self.leftHanded = False
        # thread scaling for 3D printers
        # scaled_diam = diam * ScaleA + ScaleB
        self.sm3DPrintMode = False
        self.smNutThrScaleA = 1.0
        self.smNutThrScaleB = 0.0
        self.smScrewThrScaleA = 1.0
        self.smScrewThrScaleB = 0.0

    def createScrew(self, function, fastenerAttribs):
        # self.simpThread = self.SimpleScrew.isChecked()
        # self.symThread = self.SymbolThread.isChecked()
        # FreeCAD.Console.PrintMessage(NL_text + "\n")
        if not self.objAvailable:
            return None
        try:
            if fastenerAttribs.calc_len is not None:
                fastenerAttribs.calc_len = self.getLength(fastenerAttribs.calc_len)
            if not hasattr(self, function):
                module = "FsFunctions.FS" + function
                setattr(Screw, function, getattr(importlib.import_module(module), function))
        except ValueError:
            # print "Error! nom_dia and length values must be valid numbers!"
            FreeCAD.Console.PrintMessage("Error! nom_dia and length values must be valid numbers!\n")
            return None


        if (fastenerAttribs.diameter == "Custom"):
             fastenerAttribs.dimTable = None
        else:
             fastenerAttribs.dimTable = FsData[fastenerAttribs.type + "def"][fastenerAttribs.diameter]
        self.leftHanded = fastenerAttribs.leftHanded
        # self.fastenerLen = l
        # fa.type = ST_text
        # fa.calc_diam = ND_text
        # self.customPitch = customPitch
        # self.customDia = customDia
        doc = FreeCAD.activeDocument()

        if function != "" :
            function = "self." + function + "(fastenerAttribs)"
            screw = eval(function)
            done = True
        else:
            FreeCAD.Console.PrintMessage("No suitable function for " + fastenerAttribs.type + " Screw Type!\n")
            return None
        #Part.show(screw)    
        return screw
        
    # DIN 7998 Wood Thread
    # zs: z position of start of the threaded part
    # ze: z position of end of the flat portion of screw (just where the tip starts) 
    # zt: z position of screw tip
    # ro: outer radius
    # ri: inner radius
    # p:  thread pitch
    def makeDin7998Thread(self, zs, ze, zt, ri, ro, p):
        epsilon = 0.03                          # epsilon needed since OCCT struggle to handle overlaps
        tph = ro - ri                           # thread profile height
        tphb = tph / math.tan(math.radians(60)) # thread profile half base
        tpratio = 0.5                           # size ratio between tip start thread and standard thread 
        tph2 = tph * tpratio
        tphb2 = tphb * tpratio
        tipH = ze - zt

        # tip thread profile
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoints((0.0, -tphb2), (0.0, tphb2), (2.0 * tphb2, tphb2))
        aWire = fm.GetClosedWire()
        aWire.translate(FreeCAD.Vector(epsilon, 0.0, 3.0 * tphb2))

        # top thread profile
        fm.Reset()
        fm.AddPoints((0.0, -tphb), (0.0, tphb), (tph, 0.0))
        bWire = fm.GetClosedWire()
        bWire.translate(FreeCAD.Vector(ri - epsilon, 0.0, tphb + tipH))
        
        # create helix for tip thread part
        numTurns = math.floor(tipH / p)
        #Part.show(hlx)
        hlx = Part.makeLongHelix(p, numTurns * p, 5, 0, self.leftHanded)
        sweep = Part.BRepOffsetAPI.MakePipeShell(hlx)
        sweep.setFrenetMode(True)
        sweep.setTransitionMode(1)  # right corner transition
        sweep.add(aWire)
        sweep.add(bWire)
        if sweep.isReady():
            sweep.build()
            sweep.makeSolid()
            tip_solid = sweep.shape()
            tip_solid.translate(FreeCAD.Vector(0.0, 0.0, zt))
            #Part.show(tip_solid)
        else:
            raise RuntimeError("Failed to create woodscrew tip thread")

        # create helix for body thread part
        hlx = Part.makeLongHelix(p, zs - ze, 5, 0, self.leftHanded)
        hlx.translate(FreeCAD.Vector(0.0, 0.0, tipH))
        sweep = Part.BRepOffsetAPI.MakePipeShell(hlx)
        sweep.setFrenetMode(True)
        sweep.setTransitionMode(1)  # right corner transition
        sweep.add(bWire)
        if sweep.isReady():
            sweep.build()
            sweep.makeSolid()
            body_solid = sweep.shape()
            body_solid.translate(FreeCAD.Vector(0.0, 0.0, zt))
            #Part.show(body_solid)
        else:
            raise RuntimeError("Failed to create woodscrew body thread")

        thread_solid = body_solid.fuse(tip_solid)
        # rotate the thread solid to prevent OCC errors due to cylinder seams aligning
        thread_solid.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        #Part.show(thread_solid, "thread_solid")
        return thread_solid


    def makeHextool(self, s_hex, k_hex, cir_hex):
        # makes a cylinder with an inner hex hole, used as cutting tool
        # create hexagon face
        mhex = Base.Matrix()
        mhex.rotateZ(math.radians(60.0))
        polygon = []
        vhex = Base.Vector(s_hex / math.sqrt(3.0), 0.0, -k_hex * 0.1)
        for i in range(6):
            polygon.append(vhex)
            vhex = mhex.multiply(vhex)
        polygon.append(vhex)
        hexagon = Part.makePolygon(polygon)
        hexagon = Part.Face(hexagon)

        # create circle face
        circ = Part.makeCircle(cir_hex / 2.0, Base.Vector(0.0, 0.0, -k_hex * 0.1))
        circ = Part.Face(Part.Wire(circ))

        # Create the face with the circle as outline and the hexagon as hole
        face = circ.cut(hexagon)

        # Extrude in z to create the final cutting tool
        exHex = face.extrude(Base.Vector(0.0, 0.0, k_hex * 1.2))
        # Part.show(exHex)
        return exHex

    def GetInnerThreadMinDiameter(self, dia, P, addEpsilon = 0.001):
        H = P * cos30  # Thread depth H
        return dia - H * 5.0 / 4.0 + addEpsilon

    def CreateInnerThreadCutter(self, dia, P, blen):
        H = P * cos30  # Thread depth H
        r = dia / 2.0

        height = (blen // P) + 2

        helix = Part.makeLongHelix(P, height, dia * self.Tuner / 1000.0, 0, self.leftHanded)  # make just one turn, length is identical to pitch
        helix.translate(FreeCAD.Vector(0.0, 0.0, -P * 9.0 / 16.0))

        # points for inner thread profile
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoint(r - H * 5.0 / 8.0, P * 7.0 / 16.0)
        fm.AddPoint(r, P * 2.0 / 16.0)
        fm.AddArc(r + H * 1 / 24.0, P * 2.0 / 32.0, r, 0)
        fm.AddPoint(r - H * 5.0 / 8.0, -P * 5.0 / 16.0)
        W0 = fm.GetClosedWire()
        W0.translate(Base.Vector(0,0,-P))

        makeSolid = True
        isFrenet = True
        cutTool = Part.Wire(helix).makePipeShell([W0], makeSolid, isFrenet)
        #Part.show(cutTool, 'cutTool')
        return cutTool

    def CreateThreadCutter(self, dia, P, blen):
        # make a cylindrical solid, then cut the thread profile from it
        H = math.sqrt(3) / 2 * P
        # move the very bottom of the base up a tiny amount
        # prevents some too-small edges from being created
        trotations = blen // P + 1

        # create a sketch profile of the thread
        # ref: https://en.wikipedia.org/wiki/ISO_metric_screw_thread
        fillet_r = P * math.sqrt(3) / 12
        helix_height = trotations * P
        dia2 = dia / 2
 
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoint(dia2 + sqrt3 * 3 / 80 * P, -0.475 * P)
        fm.AddPoint(dia2 - 0.625 * H, -1 * P / 8)
        fm.AddArc(dia2 - 0.625 * H - 0.5 * fillet_r, 0, dia2 - 0.625 * H, P / 8)
        fm.AddPoint(dia2 + sqrt3 * 3 / 80 * P, 0.475 * P)
        thread_profile_wire = fm.GetClosedWire()
        thread_profile_wire.translate(Base.Vector(0, 0, -1 * helix_height))
        # make the helical paths to sweep along
        # NOTE: makeLongHelix creates slightly conical
        # helices unless the 4th parameter is set to 0!
        main_helix = Part.makeLongHelix(P, helix_height, dia / 2, 0, self.leftHanded)
        lead_out_helix = Part.makeLongHelix(P, P / 2, dia / 2 + 0.5 * (5 / 8 * H + 0.5 * fillet_r), 0, self.leftHanded)
        main_helix.rotate(Base.Vector(0, 0, 0), Base.Vector(1, 0, 0), 180)
        lead_out_helix.translate(Base.Vector(0.5 * (-1 * (5 / 8 * H + 0.5 * fillet_r)), 0, 0))
        sweep_path = Part.Wire([main_helix, lead_out_helix])
        # use Part.BrepOffsetAPI to sweep the thread profile
        # ref: https://forum.freecadweb.org/viewtopic.php?t=21636#p168339
        sweep = Part.BRepOffsetAPI.MakePipeShell(sweep_path)
        sweep.setFrenetMode(True)
        sweep.setTransitionMode(1)  # right corner transition
        sweep.add(thread_profile_wire)
        if sweep.isReady():
            sweep.build()
        else:
            # geometry couldn't be generated in a usable form
            raise RuntimeError("Failed to create shell thread: could not sweep thread")
        sweep.makeSolid()
        return sweep.shape()

    def RevolveZ(self, profile, angle = 360):
        return profile.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), angle)
        
    def makeShellthread(self, dia, P, blen, withcham, ztop, tlen = -1):
        """
        Construct a 60 degree screw thread with diameter dia,
        pitch P. 
        blen is the length of the shell body.
        tlen is the length of the threaded part (-1 = same as body length).
        if withcham == True, the end of the thread is nicely chamfered.
        The thread is constructed z-up, as a shell, with the top circular
        face removed. The top of the shell is centered @ (0, 0, ztop)
        """
        correction = 1e-5
        if tlen < 0:
            tlen = blen
        dia2 = dia / 2
        corr_blen = blen - correction
        
        # create base body
        pnt0 = (dia2, 0)
        pnt1 = (dia2,  -blen + P / 2)
        pnt2 = (dia2 - P / 2, -corr_blen)
        pnt3 = (0, -corr_blen)
        pnt4 = (0, 0)
        pnt5 = (dia2, -corr_blen)
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoints(pnt0)
        if withcham:
            fm.AddPoints(pnt1, pnt2)
        else:
            fm.AddPoints(pnt5)
        fm.AddPoints(pnt3, pnt4)

        base_profile = fm.GetClosedWire()
        base_shell = self.RevolveZ(base_profile)
        base_body = Part.makeSolid(base_shell)

        swept_solid = self.CreateThreadCutter(dia, P, blen)
        # translate swept path slightly for backwards compatibility
        toffset = blen - tlen + P / 2
        minoffset = 5 * P / 8
        if (toffset < minoffset):
            toffset = minoffset

        swept_solid.translate(Base.Vector(0, 0, -toffset))
        # perform the actual boolean operations
        base_body.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 90)
        threaded_solid = base_body.cut(swept_solid)
        if toffset < 0:
            # one more component: a kind of 'cap' to improve behaviour with large offset values
            # (shai: this feature in unused??)
            fm.Reset()
            fm.AddPoints(pnt4, pnt0, (0, -dia2))
            cap_profile = fm.GetClosedWire()
            cap_shell = self.RevolveZ(cap_profile)
            cap_solid = Part.makeSolid(cap_shell)
            # threaded_solid = threaded_solid.fuse(cap_solid)
            # threaded_solid.removeSplitter
        # remove top face(s) and convert to a shell
        result = Part.Shell([x for x in threaded_solid.Faces \
                             if not abs(x.CenterOfMass[2]) < 1e-7])
        result.translate(Base.Vector(0, 0, ztop))
        return result

    # if da is not None: make Shell for a nut else: make a screw tap
    def makeInnerThread_2(self, d, P, rotations, da, l):
        d = float(d)
        bot_off = 0.0  # nominal length

        # if d > 52.0:
        #     fuzzyValue = 5e-5
        # else:
        #     fuzzyValue = 0.0

        fuzzyValue = 5e-4

        H = P * cos30  # Thread depth H
        r = d / 2.0

        helix = Part.makeLongHelix(P, P, d * self.Tuner / 1000.0, 0, self.leftHanded)  # make just one turn, length is identical to pitch
        helix.translate(FreeCAD.Vector(0.0, 0.0, -P * 9.0 / 16.0))

        # points for inner thread profile
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoint(r, 0.0)
        fm.AddPoint(r - H * 5.0 / 8.0, -P * 5.0 / 16.0)
        fm.AddPoint(r - H * 5.0 / 8.0, -P * 9.0 / 16.0)
        fm.AddPoint(r, -P * 14.0 / 16.0)
        fm.AddArc(r + H * 1 / 24.0, -P * 31.0 / 32.0, r, -P)
        W0 = fm.GetWire()
        # Part.show(W0, 'W0')
        # self.CreateInnerThreadCutter(d, P, 5 * P)

        makeSolid = False
        isFrenet = True
        TheShell = Part.Wire(helix).makePipeShell([W0], makeSolid, isFrenet)
        TheFaces = TheShell.Faces

        if da is None:
            commonbox = Part.makeBox(d + 4.0 * P, d + 4.0 * P, 3.0 * P)
            commonbox.translate(FreeCAD.Vector(-(d + 4.0 * P) / 2.0, -(d + 4.0 * P) / 2.0, -(3.0) * P))
            topShell = TheShell.common(commonbox)
            top_edges = []
            top_z = -1.0e-5

            for kante in topShell.Edges:
                if kante.Vertexes[0].Point.z >= top_z and kante.Vertexes[1].Point.z >= top_z:
                    top_edges.append(kante)
                    # Part.show(kante)
            top_wire = Part.Wire(Part.__sortEdges__(top_edges))
            top_face = Part.Face(top_wire)

            TheFaces = [top_face.Faces[0]]
            TheFaces.extend(topShell.Faces)

            for i in range(rotations - 2):
                TheShell.translate(FreeCAD.Vector(0.0, 0.0, - P))
                for flaeche in TheShell.Faces:
                    TheFaces.append(flaeche)

            # FreeCAD.Console.PrintMessage("Base-Shell: " + str(i) + "\n")
            # Make separate faces for the tip of the screw
            botFaces = []
            for i in range(rotations - 2, rotations, 1):
                TheShell.translate(FreeCAD.Vector(0.0, 0.0, - P))

                for flaeche in TheShell.Faces:
                    botFaces.append(flaeche)
            # FreeCAD.Console.PrintMessage("Bottom-Shell: " + str(i) + "\n")
            # FreeCAD.Console.PrintMessage("without chamfer: " + str(i) + "\n")

            commonbox = Part.makeBox(d + 4.0 * P, d + 4.0 * P, 3.0 * P)
            commonbox.translate(FreeCAD.Vector(-(d + 4.0 * P) / 2.0, -(d + 4.0 * P) / 2.0, -(rotations) * P + bot_off))
            # commonbox.translate(FreeCAD.Vector(-(d+4.0*P)/2.0, -(d+4.0*P)/2.0,-(rotations+3)*P+bot_off))
            # Part.show(commonbox)

            BotShell = Part.Shell(botFaces)
            # Part.show(BotShell)

            BotShell = BotShell.common(commonbox)
            # BotShell = BotShell.cut(commonbox)
            bot_edges = []
            bot_z = 1.0e-5 - (rotations) * P + bot_off

            for kante in BotShell.Edges:
                if kante.Vertexes[0].Point.z <= bot_z and kante.Vertexes[1].Point.z <= bot_z:
                    bot_edges.append(kante)
                    # Part.show(kante)
            bot_wire = Part.Wire(Part.__sortEdges__(bot_edges))

            bot_face = Part.Face(bot_wire)
            bot_face.reverse()

            for flaeche in BotShell.Faces:
                TheFaces.append(flaeche)
            # if da is not None:
            # for flaeche in cham_Shell.Faces:
            # TheFaces.append(flaeche)
            # else:
            TheFaces.append(bot_face)
            TheShell = Part.Shell(TheFaces)
            TheSolid = Part.Solid(TheShell)
            # print self.Tuner, " ", TheShell.ShapeType, " ", TheShell.isValid(), " rotations: ", rotations, " Shellpoints: ", len(TheShell.Vertexes)
            return TheSolid

        else:
            # Try to make the inner thread shell of a nut
            cham_i = 2 * H * math.tan(math.radians(15.0))  # inner chamfer

            # points for chamfer: cut-Method
            fm = FastenerBase.FSFaceMaker()
            da2 = da / 2.0
            fm.AddPoint(da2 - 2 * H, +cham_i)
            fm.AddPoint(da2, 0.0)
            fm.AddPoint(da2, - 2.1 * P)
            fm.AddPoint(da2 - 2 * H, - 2.1 * P)
            bottom_Face = fm.GetFace()
            bottom_Solid = self.RevolveZ(bottom_Face)
            # Part.show(cham_Solid, 'cham_Solid')
            # Part.show(Wch_wire)
            bottomChamferFace = bottom_Solid.Faces[0]

            # points for chamfer: cut-Method
            fm.StartPoint(da / 2.0 - 2 * H, l - cham_i)
            fm.AddPoint(da / 2.0, l)
            fm.AddPoint(da / 2.0, l + 4 * P)
            fm.AddPoint(da / 2.0 - 2 * H, l + 4 * P)
            top_Face = fm.GetFace()

            top_Solid = self.RevolveZ(top_Face)
            # Part.show(top_Solid, 'top_Solid')
            # Part.show(Wch_wire)
            topChamferFace = top_Solid.Faces[0]

            threeThreadFaces = TheFaces.copy()

            for k in range(1):
                TheShell.translate(FreeCAD.Vector(0.0, 0.0, P))
                for threadFace in TheShell.Faces:
                    threeThreadFaces.append(threadFace)

            chamferShell = Part.Shell(threeThreadFaces)
            # Part.show(chamferShell, 'chamferShell')
            # Part.show(bottomChamferFace, 'bottomChamferFace')

            bottomPart = chamferShell.cut(bottom_Solid)
            # Part.show(bottomPart, 'bottomPart')
            # chamferShell.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 90)
            bottomFuse, bottomMap = bottomChamferFace.generalFuse([chamferShell], fuzzyValue)
            # print ('bottomMap: ', bottomMap)
            # chamFuse, chamMap = chamferShell.generalFuse([bottomChamferFace])
            # print ('chamMap: ', chamMap)
            # Part.show(bottomFuse, 'bottomFuse')
            # Part.show(bottomMap[0][0], 'bMap0')
            # Part.show(bottomMap[0][1], 'bMap1')
            if len(bottomMap[0]) < 2:
                return None
            innerThreadFaces = [bottomMap[0][1]]
            for face in bottomPart.Faces:
                innerThreadFaces.append(face)
            # bottomShell = Part.Shell(innerThreadFaces)
            # Part.show(bottomShell)
            bottomFaces = []
            # TheShell.translate(FreeCAD.Vector(0.0, 0.0, P))
            for k in range(1, rotations - 2):
                TheShell.translate(FreeCAD.Vector(0.0, 0.0, P))
                for threadFace in TheShell.Faces:
                    innerThreadFaces.append(threadFace)
            testShell = Part.Shell(innerThreadFaces)
            # Part.show(testShell, 'testShell')

            chamferShell.translate(FreeCAD.Vector(0.0, 0.0, (rotations - 1) * P))
            # Part.show(chamferShell, 'chamferShell')
            # Part.show(topChamferFace, 'topChamferFace')
            topPart = chamferShell.cut(top_Solid) 
            # FreeCAD.Console.PrintMessage("chamferShell: " + str(len(chamferShell.Faces)) + " faces, topPart: " + str(len(topPart.Faces)) + " faces\n")
            if len(topPart.Faces) >len(chamferShell.Faces):
                # cut operation failed
                return None
            # Part.show(topPart, 'topPart')
            for face in topPart.Faces:
                innerThreadFaces.append(face)

            topFuse, topMap = topChamferFace.generalFuse([chamferShell], fuzzyValue)
            # print ('topMap: ', topMap)
            # Part.show(topMap[0][0], 'tMap0')
            # Part.show(topMap[0][1], 'tMap1')
            # Part.show(topFuse, 'topFuse')
            if len(topMap[0]) < 2:
                return None
            innerThreadFaces.append(topMap[0][1])

            # topFaces = []
            # for face in topPart.Faces:
            #  topFaces.append(face)
            # topFaces.append(topMap[0][1])
            # testTopShell = Part.Shell(topFaces)
            # Part.show(testTopShell, 'testTopShell')

            threadShell = Part.Shell(innerThreadFaces)
            # Part.show(threadShell, 'threadShell')

            return threadShell




    def cutChamfer(self, dia_cC, P_cC, l_cC):
        key, res = FastenerBase.FSGetKey("CrhamferTool", dia_cC, P_cC, l_cC)
        if res is not None:
            return res
        # FastenerBase.FSCache[key] = cyl
        cham_t = P_cC * sqrt3 / 2.0 * 17.0 / 24.0
        dia_cC2 = dia_cC / 2.0
        fm = FastenerBase.FSFaceMaker()
        fm.AddPoint(0.0, -l_cC)
        fm.AddPoint(dia_cC2 - cham_t, -l_cC)
        fm.AddPoint(dia_cC2 + cham_t, -l_cC + cham_t + cham_t)
        fm.AddPoint(dia_cC2 + cham_t, -l_cC - P_cC - cham_t)
        fm.AddPoint(0.0, -l_cC - P_cC - cham_t)

        CFace = fm.GetFace()
        cyl = self.RevolveZ(CFace)
        FastenerBase.FSCache[key] = cyl
        return cyl

    # cross recess type H
    def makeCross_H3(self, CrossType='2', m=6.9, h=0.0):
        key, res = FastenerBase.FSGetKey("CrossRecess", CrossType, m, h)
        if res is not None:
            return res
        # m = diameter of cross at top of screw at reference level for penetration depth
        b, e_mean, g, f_mean, r, t1, alpha, beta = FsData["iso4757def"][CrossType]

        rad265 = math.radians(26.5)
        rad28 = math.radians(28.0)
        tg = (m - g) / 2.0 / math.tan(rad265)  # depth at radius of g
        t_tot = tg + g / 2.0 * math.tan(rad28)  # total depth

        # print 'tg: ', tg,' t_tot: ', t_tot
        hm = m / 4.0
        hmc = m / 2.0
        rmax = m / 2.0 + hm * math.tan(rad265)

        fm = FastenerBase.FSFaceMaker()
        fm.AddPoints((0.0, hm), (rmax, hm), (g / 2.0, -tg), (0.0, -t_tot))
        aWire = fm.GetWire()
        crossShell = self.RevolveZ(aWire)
        # FreeCAD.Console.PrintMessage("Peak-wire revolved: " + str(e_mean) + "\n")
        cross = Part.Solid(crossShell)
        # Part.show(cross)

        # the need to cut 4 corners out of the above shape.
        # Definition of corner
        # The angles 92 degrees and alpha are defined on a plane which has
        # an angle of beta against our coordinate system.
        # The projected angles are needed for easier calculation!
        rad_alpha = math.radians(alpha / 2.0)
        rad92 = math.radians(92.0 / 2.0)
        rad_beta = math.radians(beta)

        rad_alpha_p = math.atan(math.tan(rad_alpha) / math.cos(rad_beta))
        rad92_p = math.atan(math.tan(rad92) / math.cos(rad_beta))

        tb = tg + (g - b) / 2.0 * math.tan(rad28)  # depth at dimension b
        rbtop = b / 2.0 + (hmc + tb) * math.tan(rad_beta)  # radius of b-corner at hm
        rbtot = b / 2.0 - (t_tot - tb) * math.tan(rad_beta)  # radius of b-corner at t_tot

        dre = e_mean / 2.0 / math.tan(rad_alpha_p)  # delta between corner b and corner e in x direction
        # FreeCAD.Console.PrintMessage("delta calculated: " + str(dre) + "\n")

        dx = m / 2.0 * math.cos(rad92_p)
        dy = m / 2.0 * math.sin(rad92_p)

        PntC0 = Base.Vector(rbtop, 0.0, hmc)
        PntC1 = Base.Vector(rbtot, 0.0, -t_tot)
        PntC3 = Base.Vector(rbtot + dre, +e_mean / 2.0, -t_tot)
        PntC5 = Base.Vector(rbtot + dre, -e_mean / 2.0, -t_tot)
        PntC7 = Base.Vector(rbtot + dre + 2.0 * dx, +e_mean + 2.0 * dy, -t_tot)
        PntC9 = Base.Vector(rbtot + dre + 2.0 * dx, -e_mean - 2.0 * dy, -t_tot)

        wire_t_tot = Part.makePolygon([PntC1, PntC3, PntC7, PntC9, PntC5, PntC1])
        # Part.show(wire_t_tot)
        edgeC1 = Part.makeLine(PntC0, PntC1)
        # FreeCAD.Console.PrintMessage("edgeC1 with PntC9" + str(PntC9) + "\n")

        makeSolid = True
        isFrenet = False
        corner = Part.Wire(edgeC1).makePipeShell([wire_t_tot], makeSolid, isFrenet)
        # Part.show(corner)

        rot_axis = Base.Vector(0., 0., 1.0)
        sin_res = math.sin(math.radians(90) / 2.0)
        cos_res = math.cos(math.radians(90) / 2.0)
        rot_axis.multiply(-sin_res)  # Calculation of Quaternion-Elements
        # FreeCAD.Console.PrintMessage("Quaternion-Elements" + str(cos_res) + "\n")

        pl_rot = FreeCAD.Placement()
        pl_rot.Rotation = (rot_axis.x, rot_axis.y, rot_axis.z, cos_res)  # Rotation-Quaternion 90° z-Axis

        crossShell = crossShell.cut(corner)
        # Part.show(crossShell)
        cutplace = corner.Placement

        cornerFaces = []
        cornerFaces.append(corner.Faces[0])
        cornerFaces.append(corner.Faces[1])
        cornerFaces.append(corner.Faces[3])
        cornerFaces.append(corner.Faces[4])

        cornerShell = Part.Shell(cornerFaces)
        cornerShell = cornerShell.common(cross)
        addPlace = cornerShell.Placement

        crossFaces = cornerShell.Faces

        for i in range(3):
            cutplace.Rotation = pl_rot.Rotation.multiply(corner.Placement.Rotation)
            corner.Placement = cutplace
            crossShell = crossShell.cut(corner)
            addPlace.Rotation = pl_rot.Rotation.multiply(cornerShell.Placement.Rotation)
            cornerShell.Placement = addPlace
            for coFace in cornerShell.Faces:
                crossFaces.append(coFace)

        # Part.show(crossShell)
        for i in range(1, 6):
            crossFaces.append(crossShell.Faces[i])

        crossShell0 = Part.Shell(crossFaces)

        crossFaces.append(crossShell.Faces[0])
        crossShell = Part.Shell(crossFaces)

        cross = Part.Solid(crossShell)

        # FreeCAD.Console.PrintMessage("Placement: " + str(pl_rot) + "\n")

        cross.Placement.Base = Base.Vector(0.0, 0.0, h)
        crossShell0.Placement.Base = Base.Vector(0.0, 0.0, h)
        # Part.show(crossShell0)
        # Part.show(cross)
        FastenerBase.FSCache[key] = (cross, crossShell0)
        return cross, crossShell0

    # Allen recess cutting tool
    # Parameters used: s_mean, k, t_min, dk
    def makeAllen2(self, s_a=3.0, t_a=1.5, h_a=2.0, t_2=0.0):
        # h_a  top height location of cutting tool
        # s_a hex width
        # t_a dept of the allen
        # t_2 depth of center-bore

        key, res = FastenerBase.FSGetKey("Allen2Tool", s_a, t_a, h_a, t_2)
        if res is not None:
            # reset placement should original objects were moved
            res[0].Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,h_a),FreeCAD.Rotation(0,0,0,1))
            res[1].Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,h_a),FreeCAD.Rotation(0,0,0,1))
            return res

        fm = FastenerBase.FSFaceMaker()
        if t_2 == 0.0:
            depth = s_a / 3.0
            e_cham = 2.0 * s_a / math.sqrt(3.0)
            # FreeCAD.Console.PrintMessage("allen tool: " + str(s_a) + "\n")

            # Points for an arc at the peak of the cone
            rCone = e_cham / 4.0
            hyp = (depth * math.sqrt(e_cham ** 2 / depth ** 2 + 1.0) * rCone) / e_cham
            radAlpha = math.atan(e_cham / depth)
            radBeta = math.pi / 2.0 - radAlpha
            zrConeCenter = hyp - depth - t_a
            xArc1 = math.sin(radBeta) * rCone
            zArc1 = zrConeCenter - math.cos(radBeta) * rCone
            xArc2 = math.sin(radBeta / 2.0) * rCone
            zArc2 = zrConeCenter - math.cos(radBeta / 2.0) * rCone
            zArc3 = zrConeCenter - rCone

            # The round part of the cutting tool, we need for the allen hex recess
            fm.AddPoint(0.0, -t_a - depth - depth)
            fm.AddPoint(e_cham, -t_a - depth - depth)
            fm.AddPoint(e_cham, -t_a + depth)
            fm.AddPoint(xArc1, zArc1)
            fm.AddArc(xArc2, zArc2, 0.0, zArc3) 
            hex_depth = -1.0 - t_a - depth * 1.1
        else:
            e_cham = 2.0 * s_a / math.sqrt(3.0)
            d_cent = s_a / 3.0
            depth_cent = d_cent * math.tan(math.pi / 6.0)
            depth_cham = (e_cham - d_cent) * math.tan(math.pi / 6.0)

            fm.AddPoint(0.0, -t_2 - depth_cent)
            fm.AddPoint(0.0, -t_2 - depth_cent - depth_cent)
            fm.AddPoint(e_cham, -t_2 - depth_cent - depth_cent)
            fm.AddPoint(e_cham, -t_a + depth_cham)
            fm.AddPoint(d_cent, -t_a)
            fm.AddPoint(d_cent, -t_2)
            hex_depth = -1.0 - t_2 - depth_cent * 1.1

        hFace = fm.GetFace()
        roundtool = self.RevolveZ(hFace)

        # create hexagon
        mhex = Base.Matrix()
        mhex.rotateZ(math.radians(60.0))
        polygon = []
        vhex = Base.Vector(s_a / math.sqrt(3.0), 0.0, 1.0)
        for i in range(6):
            polygon.append(vhex)
            vhex = mhex.multiply(vhex)
        polygon.append(vhex)
        hexagon = Part.makePolygon(polygon)
        hexFace = Part.Face(hexagon)
        solidHex = hexFace.extrude(Base.Vector(0.0, 0.0, hex_depth))
        allen = solidHex.cut(roundtool)
        # Part.show(allen)

        allenFaces = [allen.Faces[0]]
        for i in range(2, len(allen.Faces)):
            allenFaces.append(allen.Faces[i])
        allenShell = Part.Shell(allenFaces)
        solidHex.Placement.Base = Base.Vector(0.0, 0.0, h_a)
        allenShell.Placement.Base = Base.Vector(0.0, 0.0, h_a)

        FastenerBase.FSCache[key] = (solidHex, allenShell)
        return solidHex, allenShell

    # ISO 10664 Hexalobular internal driving feature for bolts and screws
    def makeIso10664_3(self, RType='T20', t_hl=3.0, h_hl=0):
        # t_hl depth of the recess
        # h_hl top height location of Cutting tool

        key, res = FastenerBase.FSGetKey("HexalobularTool", RType, t_hl, h_hl)
        if res is not None:
            return res

        A, B, Re = FsData["iso10664def"][RType]
        sqrt_3 = math.sqrt(3.0)
        depth = A / 4.0
        offSet = 1.0


        # Chamfer cutter for the hexalobular recess
        # Points for an arc at the peak of the cone
        rCone = A / 4.0
        hyp = (depth * math.sqrt(A ** 2 / depth ** 2 + 1.0) * rCone) / A
        radAlpha = math.atan(A / depth)
        radBeta = math.pi / 2.0 - radAlpha
        zrConeCenter = hyp - depth - t_hl
        xArc1 = math.sin(radBeta) * rCone
        zArc1 = zrConeCenter - math.cos(radBeta) * rCone
        xArc2 = math.sin(radBeta / 2.0) * rCone
        zArc2 = zrConeCenter - math.cos(radBeta / 2.0) * rCone
        zArc3 = zrConeCenter - rCone

        fm = FastenerBase.FSFaceMaker()
        fm.AddPoint(0.0, -t_hl - depth - 1.0)
        fm.AddPoint(A, -t_hl - depth - 1.0)
        fm.AddPoint(A, -t_hl + depth)
        fm.AddPoint(xArc1, zArc1)
        fm.AddArc(xArc2, zArc2, 0.0, zArc3)

        hFace = fm.GetFace()
        cutTool = self.RevolveZ(hFace)

        Ri = -((B + sqrt_3 * (2. * Re - A)) * B + (A - 4. * Re) * A) / (4. * B - 2. * sqrt_3 * A + (4. * sqrt_3 - 8.) * Re)
        # print '2nd  Ri last solution: ', Ri
        beta = math.acos(A / (4 * Ri + 4 * Re) - (2 * Re) / (4 * Ri + 4 * Re)) - math.pi / 6
        # print 'beta: ', beta
        Rh = (sqrt_3 * (A / 2.0 - Re)) / 2.0
        Re_x = A / 2.0 - Re + Re * math.sin(beta)
        Re_y = Re * math.cos(beta)
        Ri_y = B / 4.0
        Ri_x = sqrt_3 * B / 4.0

        mhex = Base.Matrix()
        mhex.rotateZ(math.radians(60.0))
        hexlobWireList = []

        PntRe0 = Base.Vector(Re_x, -Re_y, offSet)
        PntRe1 = Base.Vector(A / 2.0, 0.0, offSet)
        PntRe2 = Base.Vector(Re_x, Re_y, offSet)
        edge0 = Part.Arc(PntRe0, PntRe1, PntRe2).toShape()
        # Part.show(edge0)
        hexlobWireList.append(edge0)

        PntRi = Base.Vector(Ri_x, Ri_y, offSet)
        PntRi2 = mhex.multiply(PntRe0)
        edge1 = Part.Arc(PntRe2, PntRi, PntRi2).toShape()
        # Part.show(edge1)
        hexlobWireList.append(edge1)

        for i in range(5):
            PntRe1 = mhex.multiply(PntRe1)
            PntRe2 = mhex.multiply(PntRe2)
            edge0 = Part.Arc(PntRi2, PntRe1, PntRe2).toShape()
            hexlobWireList.append(edge0)
            PntRi = mhex.multiply(PntRi)
            PntRi2 = mhex.multiply(PntRi2)
            if i == 5:
                edge1 = Part.Arc(PntRe2, PntRi, PntRe0).toShape()
            else:
                edge1 = Part.Arc(PntRe2, PntRi, PntRi2).toShape()
            hexlobWireList.append(edge1)
        hexlobWire = Part.Wire(hexlobWireList)
        # Part.show(hWire)

        face = Part.Face(hexlobWire)

        # Extrude in z to create the cutting tool for the screw-head-face
        Helo = face.extrude(Base.Vector(0.0, 0.0, -t_hl - depth - offSet))
        # Make the recess-shell for the screw-head-shell

        hexlob = Helo.cut(cutTool)
        # Part.show(hexlob)
        hexlobFaces = [hexlob.Faces[0]]
        for i in range(2, 15):
            hexlobFaces.append(hexlob.Faces[i])

        hexlobShell = Part.Shell(hexlobFaces)

        hexlobShell.Placement.Base = Base.Vector(0.0, 0.0, h_hl)
        Helo.Placement.Base = Base.Vector(0.0, 0.0, h_hl)

        FastenerBase.FSCache[key] = (Helo, hexlobShell)
        return Helo, hexlobShell

    def setTuner(self, myTuner=511):
        self.Tuner = myTuner

    def getDia(self, ThreadDiam, isNut):
        if type(ThreadDiam) == type(""):
            threadstring = ThreadDiam.strip("()")
            dia = FsData["DiaList"][threadstring][0]
        else:
            dia = ThreadDiam
        if self.sm3DPrintMode:
            if isNut:
                dia = self.smNutThrScaleA * dia + self.smNutThrScaleB
            else:
                dia = self.smScrewThrScaleA * dia + self.smScrewThrScaleB
        return dia

    def getLength(self, LenStr):
        # washers and nuts pass an int (1), for their unused length attribute
        # handle this circumstance if necessary
        if type(LenStr) == int:
            return LenStr
        # otherwise convert the string to a number using predefined rules
        if 'in' not in LenStr:
            LenFloat = float(LenStr)
        else:
            components = LenStr.strip('in').split(' ')
            total = 0
            for item in components:
                if '/' in item:
                    subcmpts = item.split('/')
                    total += float(subcmpts[0]) / float(subcmpts[1])
                else:
                    total += float(item)
            LenFloat = total * 25.4
        return LenFloat
