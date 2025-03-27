from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

# Script "Global variables"
# Operations
targetTemperature = 18.3333  # deg C (65 deg F)
maxOpElev = 401.  # maximum allowed elevation (ft)
minOpElev = 331.5  # minimum allowed elevation (ft) (when it is acceptable to go to 317?)
# Variable names
globalVarNameMuniFlow = 'Muni_specified_flow'
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

    globVar = network.getGlobalVariable(globalVarNameMuniFlow)
    if not globVar:
        raise NameError("Global variable: " + globalVarNameMuniFlow + " not found.")
    flowVal = globVar.getCurrentValue(currentRuntimestep)
    if not isValidValue(flowVal):
        raise ValueError("Global variable: " + globalVarNameMuniFlow + " has invalid value " +
                         str(flowVal) + " for time step: " + str(currentRuntimestep.step))

    # Only evaluate rule if running WQ (getEvalRule) *and* compute iteration > 0
    #  (On 0th iteration, only local res decisions being evaluated and WQ is not being run yet)
    computeIter = currentRule.getComputeIteration()
    evalRule = currentRule.getEvalRule() and (computeIter >= lastIterationPassNum)
    if evalRule:
        # Get reservoir elevation
        resOp = currentRule.getController().getReservoirOp()
        res = resOp.getReservoirElement()
        resElev = res.getStorageFunction().getElevation(currentRuntimestep)
        if not isValidValue(resElev):  # try previous time step value
            prevRuntimestep = RunTimeStep(currentRuntimestep)
            prevRuntimestep.setStep(currentRuntimestep.getPrevStep())
            resElev = res.getStorageFunction().getElevation(prevRuntimestep)
        if not isValidValue(resElev):
            raise ValueError("Invalid value: " + str(resElev) +
                             " for reservoir elevation for time step: " + str(currentRuntimestep.step))

        setMuniOperation(network, currentRule, flowVal, resElev)

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
# Get the WQSubdomain object from the reservoir using the current rule
def getReservoirWQSubdomain(currentRule, network):
    resOp = currentRule.getController().getReservoirOp()
    res = resOp.getReservoirElement()
    wqRun = network.getRssRun().getWQRun()
    rssWQGeometry = wqRun.getRssWQGeometry()
    resWQGeoSubdom = rssWQGeometry.getSubdomForRSSElemId(res.getIndex())
    return resWQGeoSubdom


#######################################################################################################
# Set the TCD operation
def setMuniOperation(network, currentRule, flowVal, resElev):

	# Change withdrawal elevation based on elevation time series
    wqRun = network.getRssRun().getWQRun()
    engineAdapter = wqRun.getWQEngineAdapter()
    resOp = currentRule.getController().getReservoirOp()
    res = resOp.getReservoirElement()
    rssWQGeometry = wqRun.getRssWQGeometry()
    resWQGeoSubdom = rssWQGeometry.getWQSubdomain(res)
    wqcd = rssWQGeometry.getWQControlDevice(currentRule.getController().getReleaseElement())
    resLayerElevs = resWQGeoSubdom.getResLayerBoundaryElevs()
    layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)
    numLayers = len(resLayerElevs)-1

    # Find correct elevation - use highest possible
    targetLayer = 0
    for k in reversed(range(numLayers)):
        layerBotElev = resLayerElevs[k]
        layerTemp = layerTemps[k]
        if ((layerBotElev < maxOpElev and layerBotElev < resElev and layerTemp < targetTemperature)
            or layerBotElev < minOpElev):
            targetLayer = k
            break
    targetElev = resLayerElevs[targetLayer]

    # Fill TCD inlet flow array - only 1 inlet
    tcdFlows = []
    tcdFlows.append(flowVal)
    resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

    # Reallocate WQCD geometry in WQ Engine
    elevs = [targetElev]
    engineAdapter.reallocateWQControlDeviceElevs(resWQGeoSubdom, wqcd, len(elevs), elevs)

    return
