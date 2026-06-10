// Grasshopper Script Instance
#region Usings
using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;

using Rhino;
using Rhino.Geometry;

using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Data;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    #region Notes
    /* 
      Members:
        RhinoDoc RhinoDocument
        GH_Document GrasshopperDocument
        IGH_Component Component
        int Iteration

      Methods (Virtual & overridable):
        Print(string text)
        Print(string format, params object[] args)
        Reflect(object obj)
        Reflect(object obj, string method_name)
    */
    #endregion

    private void RunScript(object x, object y, object z, ref object a)
    {
        // RhinoCommon: build a 3D point and measure distance from origin.
        double coordinateX = Convert.ToDouble(x);
        double coordinateY = Convert.ToDouble(y);
        double coordinateZ = Convert.ToDouble(z);
        Point3d samplePoint = new Point3d(coordinateX, coordinateY, coordinateZ);
        double distanceFromOrigin = samplePoint.DistanceTo(Point3d.Origin);

        // For-loop: triangular number 1 + 2 + ... + N (N = rounded Z).
        int iterationLimit = Math.Max(0, Convert.ToInt32(Math.Round(coordinateZ)));
        double triangularNumberSum = 0.0;
        for (int iterationIndex = 1; iterationIndex <= iterationLimit; iterationIndex++)
        {
            triangularNumberSum += iterationIndex;
        }

        // Combine geometry metric and loop result.
        a = distanceFromOrigin + triangularNumberSum;
    }
}
