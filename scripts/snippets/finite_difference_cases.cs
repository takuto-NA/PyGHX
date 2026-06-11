// Responsibility: build base plus seven forward-difference scalar cases for RhinoCompute gradient evaluation.
// Grasshopper Script Instance
#region Usings
using System;
using System.Collections.Generic;
using Rhino;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    private const double FiniteDifferenceStep = 0.01;
    private const int CaseCount = 8;
    private const int DegreeOfFreedomCount = 7;

    private void RunScript(
        object X,
        object Y,
        object Z,
        object RX,
        object RY,
        object RZ,
        object RS,
        ref object positionXList,
        ref object positionYList,
        ref object positionZList,
        ref object rotationXList,
        ref object rotationYList,
        ref object rotationZList,
        ref object rsList)
    {
        double baseX = ReadNumberValue(X);
        double baseY = ReadNumberValue(Y);
        double baseZ = ReadNumberValue(Z);
        double baseRx = ReadNumberValue(RX);
        double baseRy = ReadNumberValue(RY);
        double baseRz = ReadNumberValue(RZ);
        double baseRs = ReadNumberValue(RS);

        double[][] caseValues = BuildForwardDifferenceCases(
            baseX,
            baseY,
            baseZ,
            baseRx,
            baseRy,
            baseRz,
            baseRs);

        List<double> positionXValues = new List<double>(CaseCount);
        List<double> positionYValues = new List<double>(CaseCount);
        List<double> positionZValues = new List<double>(CaseCount);
        List<double> rotationXValues = new List<double>(CaseCount);
        List<double> rotationYValues = new List<double>(CaseCount);
        List<double> rotationZValues = new List<double>(CaseCount);
        List<double> rsValues = new List<double>(CaseCount);

        for (int caseIndex = 0; caseIndex < CaseCount; caseIndex++)
        {
            double[] currentCase = caseValues[caseIndex];
            positionXValues.Add(currentCase[0]);
            positionYValues.Add(currentCase[1]);
            positionZValues.Add(currentCase[2]);
            rotationXValues.Add(currentCase[3]);
            rotationYValues.Add(currentCase[4]);
            rotationZValues.Add(currentCase[5]);
            rsValues.Add(currentCase[6]);
        }

        positionXList = positionXValues;
        positionYList = positionYValues;
        positionZList = positionZValues;
        rotationXList = rotationXValues;
        rotationYList = rotationYValues;
        rotationZList = rotationZValues;
        rsList = rsValues;
    }

    private static double[][] BuildForwardDifferenceCases(
        double baseX,
        double baseY,
        double baseZ,
        double baseRx,
        double baseRy,
        double baseRz,
        double baseRs)
    {
        double[][] caseValues = new double[CaseCount][];
        caseValues[0] = new double[]
        {
            baseX,
            baseY,
            baseZ,
            baseRx,
            baseRy,
            baseRz,
            baseRs,
        };

        for (int degreeOfFreedomIndex = 0; degreeOfFreedomIndex < DegreeOfFreedomCount; degreeOfFreedomIndex++)
        {
            double[] perturbedCase = (double[])caseValues[0].Clone();
            perturbedCase[degreeOfFreedomIndex] += FiniteDifferenceStep;
            caseValues[degreeOfFreedomIndex + 1] = perturbedCase;
        }

        return caseValues;
    }

    private static double ReadNumberValue(object rawValue)
    {
        if (rawValue == null)
        {
            return 0.0;
        }

        if (rawValue is GH_Number grasshopperNumber)
        {
            return grasshopperNumber.Value;
        }

        if (rawValue is double doubleValue)
        {
            return doubleValue;
        }

        if (rawValue is int integerValue)
        {
            return integerValue;
        }

        if (rawValue is float floatValue)
        {
            return floatValue;
        }

        return Convert.ToDouble(rawValue);
    }
}
