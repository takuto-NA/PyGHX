// Grasshopper C# Script: scale imported STEP geometry piece count by a contextual multiplier.
// Responsibility: combine Import 3DM geometry with Get Number multiplier for Context Bake output.
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
    private void RunScript(object geometry, object multiplier, ref object a)
    {
        int geometryPieceCount = CountGeometryPieces(geometry);
        double multiplierValue = Convert.ToDouble(multiplier);
        a = geometryPieceCount * multiplierValue;
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
