// Responsibility: convert eight penalty cases into one base penalty and a seven-element forward-difference gradient.
// Grasshopper Script Instance
#region Usings
using System;
using System.Collections.Generic;
using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    private const double FiniteDifferenceStep = 1.0;
    private const int CaseCount = 8;
    private const int DegreeOfFreedomCount = 7;

    private static readonly List<double> CollectedPenaltyCaseValues = new List<double>(CaseCount);
    private static int LastCollectedCaseCount = 0;

    private void RunScript(
        object penaltyCase,
        ref object penalty,
        ref object Gradient)
    {
        double penaltyCaseValue = ReadScalarNumber(penaltyCase);
        if (CollectedPenaltyCaseValues.Count == 0 || LastCollectedCaseCount >= CaseCount)
        {
            CollectedPenaltyCaseValues.Clear();
            LastCollectedCaseCount = 0;
        }

        CollectedPenaltyCaseValues.Add(penaltyCaseValue);
        LastCollectedCaseCount = CollectedPenaltyCaseValues.Count;

        if (LastCollectedCaseCount < CaseCount)
        {
            penalty = null;
            Gradient = null;
            return;
        }

        double basePenalty = CollectedPenaltyCaseValues[0];
        List<double> gradientValues = new List<double>(DegreeOfFreedomCount);
        for (int caseIndex = 1; caseIndex < CaseCount; caseIndex++)
        {
            double perturbedPenalty = CollectedPenaltyCaseValues[caseIndex];
            double gradientComponent = (perturbedPenalty - basePenalty) / FiniteDifferenceStep;
            gradientValues.Add(gradientComponent);
        }

        penalty = basePenalty;
        Gradient = gradientValues;
        CollectedPenaltyCaseValues.Clear();
        LastCollectedCaseCount = 0;
    }

    private static double ReadScalarNumber(object rawValue)
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
