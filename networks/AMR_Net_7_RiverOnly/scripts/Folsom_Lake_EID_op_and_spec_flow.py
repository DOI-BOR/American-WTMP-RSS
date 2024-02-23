from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants


#######################################################################################################
def initRuleScript(currentRule, network):

    applyRule = checkApplyRule(currentRule, network)

    # Handle case where rule is active but disabled or WQ for reservoir is not being run
    if not applyRule:
        currentRule.setEvalRule(False)
        network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
            " references Water Quality which is disabled for this simulation.")
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

    flowGlobalVarName = "EID_specified_flow"
    
    globVar = network.getGlobalVariable(flowGlobalVarName)
    if not globVar:
        raise NameError("Global variable: " + flowGlobalVarName + " not found.")
    flowVal = globVar.getCurrentValue(currentRuntimestep)
    if not isValidValue(flowVal):
        raise ValueError("Global variable: " + flowGlobalVarName + " has invalid value " +
                       str(flowVal) + " for time step: " + str(currentRuntimestep.step))

    # Only evaluate WQ part of script running WQ and computer iteration > 0
    #  (On 0th iteration, only local res decisions being evaluated and WQ is not being run yet)
    computeIter = currentRule.getComputeIteration()
    evalRule = currentRule.getEvalRule() and (computeIter > 1)
    if evalRule:
        setEIDoperation(currentRule, flowVal)

    opValue = OpValue()
    opValue.init(OpRule.RULETYPE_SPEC, flowVal)

    return opValue


#######################################################################################################
# Check whether a value is valid
def isValidValue(value):
    if value is None:
        return False
    elif value == Constants.UNDEFINED_DOUBLE:
        return False
    elif value < 0.:
        return False
    else:
        return True


#######################################################################################################
# Set the TCD operation
def setEIDoperation(currentRule, flowVal):

    # Fill TCD inlet flow array
    tcdFlows = []
    nInletLevels = 3
    # Initialize
    for j in range(nInletLevels):
        tcdFlows.append(0.0)
    # Always set at lowest level (325)
    tcdFlows[0] = flowVal
    
    resOp = currentRule.getController().getReservoirOp()
    resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

    return
