// Grasshopper C# Script: count geometry pieces imported from STEP via Import 3DM.
// Responsibility: accept imported geometry and output a numeric piece count for Context Bake.
#region Usings
using System;
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
    */
    #endregion

    private void RunScript(object geometry, ref object a)
    {
        a = CountGeometryPieces(geometry);
    }

    private static int CountGeometryPieces(object geometryValue)
    {
        if (geometryValue == null)
        {
            return 0;
        }

        if (geometryValue is string)
        {
            return 0;
        }

        if (geometryValue is IEnumerable geometryEnumerable)
        {
            int geometryPieceCount = 0;
            foreach (object geometryItem in geometryEnumerable)
            {
                if (IsGeometryPiece(geometryItem))
                {
                    geometryPieceCount += 1;
                }
            }
            return geometryPieceCount;
        }

        return IsGeometryPiece(geometryValue) ? 1 : 0;
    }

    private static bool IsGeometryPiece(object geometryItem)
    {
        if (geometryItem == null)
        {
            return false;
        }

        if (geometryItem is GH_Brep grasshopperBrep && grasshopperBrep.Value != null)
        {
            return true;
        }

        if (geometryItem is Brep rhinoBrep && rhinoBrep.IsValid)
        {
            return true;
        }

        if (geometryItem is GH_Mesh grasshopperMesh && grasshopperMesh.Value != null)
        {
            return true;
        }

        if (geometryItem is Mesh rhinoMesh && rhinoMesh.IsValid)
        {
            return true;
        }

        if (geometryItem is GH_Curve grasshopperCurve && grasshopperCurve.Value != null)
        {
            return true;
        }

        if (geometryItem is Curve rhinoCurve && rhinoCurve.IsValid)
        {
            return true;
        }

        return false;
    }
}
