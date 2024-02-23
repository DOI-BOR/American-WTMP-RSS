from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

# Variable names
globalVarNameShutterElevForecast = 'P3_shutter_elev_forecast'
globalVarNamePSFlow = 'P3_flow_forecast'
# Script constants
lastIterationPassNum = 2
# Operation variables
withdrawalPtOffset = 8.9  # in feet - distance to move withdrawal pt above shutter invert


#######################################################################################################
# Gets the allowable shutter elevations - overrides the data in the Reservoir Physical tab
def getShutterElevs():
    elevs = [307., 323., 336., 349., 362., 401.]
    return elevs


#######################################################################################################
def initRuleScript(currentRule, network):

    applyRule = checkApplyRule(currentRule, network)

    # Handle case where rule is active but disabled or WQ for reservoir is not being run
    if not applyRule:
        currentRule.setEvalRule(False)
        network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
            " references Water Quality which is disabled for this simulation. Rule will be ignored.")

    # WQ is being simulated
    else:
        # Reallocate WQCD geometry in WQ Engine to move withdrawal centerline higher
        elevs = getShutterElevs()
        nLevels = len(elevs)
        for k in range(nLevels):
            if k > 0:  # don't adjust lowest level because of penstock intakes
                elevs[k] += withdrawalPtOffset
        wqRun = network.getRssRun().getWQRun()
        rssWQGeometry = wqRun.getRssWQGeometry()
        resOp = currentRule.getController().getReservoirOp()
        res = resOp.getReservoirElement()
        resWQGeoSubdom = rssWQGeometry.getWQSubdomain(res)
        wqcd = rssWQGeometry.getWQControlDevice(currentRule.getController().getReleaseElement())
        engineAdapter = wqRun.getWQEngineAdapter()
        engineAdapter.reallocateWQControlDeviceElevs(resWQGeoSubdom, wqcd, nLevels, elevs)

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
        # Get the penstock shutter elevation (set in P1_forecast_op)
        shutterElev = getShutterElev(network, currentRuntimestep)

        # Get the penstock flow (set in P1_forecast_op)
        psFlow = getPenstockFlow(network, currentRuntimestep)

        tcdFlows = getTCDFlowsForShutterElev(psFlow, shutterElev)
        resOp = currentRule.getController().getReservoirOp()
        resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, psFlow)

        opValue = OpValue()
        opValue.init(OpRule.RULETYPE_SPEC, psFlow)
        return opValue

    else:
        return None


#######################################################################################################
# Get the forecasted penstock flow
def getPenstockFlow(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNamePSFlow)
    if not gv:
        raise NameError("Global variable: " + globalVarNamePSFlow + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Get the forecasted gate elevation
def getShutterElev(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameShutterElevForecast)
    if not gv:
        raise NameError("Global variable: " + globalVarNameShutterElevForecast + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Flow array for a given shutter elevation
def getTCDFlowsForShutterElev(psFlow, shutterElev):
    tcdFlows = []
    elevs = getShutterElevs()
    nInletLevels = len(elevs)
    for j in range(nInletLevels):
        if elevs[j] == shutterElev:
            tcdFlows.append(psFlow)
        else:
            tcdFlows.append(0.0)
    return tcdFlows
