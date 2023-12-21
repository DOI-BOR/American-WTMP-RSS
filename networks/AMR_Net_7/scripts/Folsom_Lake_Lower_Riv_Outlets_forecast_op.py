from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

# Variable names
globalVarNameLowerRivFlowHist = 'Lower_Riv_out_flow'
globalVarNameLowerRivFlowForecast = 'Lower_Riv_out_forecast_flow'
# Script constants
lastIterationPassNum = 2


#######################################################################################################
def initRuleScript(currentRule, network):

    applyRule = checkApplyRule(currentRule, network)

    # Handle case where rule is active but disabled or WQ for reservoir is not being run
    if not applyRule:
        currentRule.setEvalRule(False)
        network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() +
                                                " references Water Quality which is disabled for this simulation. Rule will be ignored.")

    return Constants.TRUE


#######################################################################################################
# This checks whether we should be applying this rule in a given simulation
# Needs to have WQ running and the reservoir in the active WQ geometry
def checkApplyRule(currentRule, network):
    wqRun = network.getWQRun()
    if not wqRun:
        return False
    rssWQGeometry = wqRun.getRssWQGeometry()
    resOp = currentRule.getController().getReservoirOp()
    res = resOp.getReservoirElement()
    resWQGeoSubdom = rssWQGeometry.getWQSubdomain(res)
    return rssWQGeometry.isInExtent(resWQGeoSubdom)


#######################################################################################################
def runRuleScript(currentRule, network, currentRuntimestep):

    # Only evaluate WQ part of script running WQ and computer iteration > 0
    #  (On 0th iteration, only local res decisions being evaluated and WQ is not being run yet)
    computeIter = currentRule.getComputeIteration()
    evalRule = currentRule.getEvalRule() and (computeIter >= lastIterationPassNum)

    if evalRule:
        # Get the forecast flow (set in P1_forecast_op)
        rivFlow = getForecastFlow(network, currentRuntimestep)
    else:
        # Get the historical flow
        rivFlow = getHistoricalFlow(network, currentRuntimestep)

    opValue = OpValue()
    opValue.init(OpRule.RULETYPE_SPEC, rivFlow)
    #network.printMessage("Setting Lower River Outlet flow: " + str(rivFlow))
    return opValue


#######################################################################################################
# Get the forecasted flow
def getForecastFlow(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameLowerRivFlowForecast)
    if not gv:
        raise NameError("Global variable: " + globalVarNameLowerRivFlowForecast + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Get the historical input flow
def getHistoricalFlow(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameLowerRivFlowHist)
    if not gv:
        raise NameError("Global variable: " + globalVarNameLowerRivFlowHist + " not found.")
    return gv.getCurrentValue(runtimeStep)
