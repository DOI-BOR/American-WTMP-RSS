from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

# Variable names
globalVarNameShutterElev = 'P2_shutter_elev'
globalVarNamePSFlow = 'P2_specified_flow'
globalVarNameLeakage = 'Folsom_leakage'
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
            " references Water Quality which is disabled for this simulation.")
        return Constants.TRUE
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
        globVar = network.getGlobalVariable(globalVarNamePSFlow)
        if not globVar:
            raise NameError("Global variable: " + globalVarNamePSFlow + " not found.")
        flowVal = globVar.getCurrentValue(currentRuntimestep)
        if not isValidValue(flowVal):
            raise ValueError("Global variable: " + globalVarNamePSFlow + " has invalid value " +
                             str(flowVal) + " for time step: " + str(currentRuntimestep.step))
    
        globVar = network.getGlobalVariable(globalVarNameShutterElev)
        if not globVar:
            raise NameError("Global variable: " + globalVarNameShutterElev + " not found.")
        elevVal = globVar.getCurrentValue(currentRuntimestep)
        if not isValidValue(elevVal):
            raise ValueError("Global variable: " + globalVarNameShutterElev + " has invalid value " +
                             str(elevVal) + " for time step: " + str(currentRuntimestep.step))
        setTCDoperation(currentRule, flowVal, elevVal)
    
        opValue = OpValue()
        opValue.init(OpRule.RULETYPE_SPEC, flowVal)
        return opValue

    else:
        return None


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
# translate the Folsom dss gate elevation to a lowest-gate leakage fraction
def getCardnoLeakageFractionFromGateElev(elevVal):
    # B = 307 -- all open
    # B1 = 323
    # M = 336
    # M(t) = 349
    # T = 362
    # A = 401  -- all closed, coming in the top
    if elevVal < 310.0:
        return 0.0
    elif elevVal < 330.0:
        return 0.08
    elif elevVal < 340.0:
        return 0.12
    elif elevVal < 350.0:
        return 0.2
    elif elevVal < 370.0:
        return 0.25
    else:
        return 0.38


#######################################################################################################
# Set the leakage global variable
def setLeakage(network, currentRuntimestep, leakage):
	gv = network.getGlobalVariable(globalVarNameLeakage)
	priorLeakage = gv.getCurrentValue(currentRuntimestep)
	priorLeakage = max(priorLeakage, 0.0)  # account for HEC undefined double
	newLeakage = priorLeakage + leakage
	gv.setCurrentValue(currentRuntimestep, newLeakage)


#######################################################################################################
# Set the TCD operation
def setTCDoperation(currentRule, flowVal, elevVal):

    # Fill TCD inlet flow array
    tcdFlows = []
    nInletLevels = 6
    # Initialize
    for j in range(nInletLevels):
        tcdFlows.append(0.0)
    # Leakage

    #tcdFlows[0] = 0.35 * flowVal
    #remainingFlow = 0.65 * flowVal

    lowerMinLeakageFlow = 44. # min cfs
    leakageFraction = getCardnoLeakageFractionFromGateElev(elevVal)
    # leakageFraction = 0.30

    if flowVal < lowerMinLeakageFlow:  # cfs
        leakage = flowVal
        remainingFlow = 0.
    else:
        leakage = lowerMinLeakageFlow + leakageFraction*(flowVal-lowerMinLeakageFlow)
        remainingFlow = (1.0-leakageFraction)*(flowVal-lowerMinLeakageFlow)
    
    tcdFlows[0] = leakage
    setLeakage(network, currentRuntimestep, leakage)

    # Set based on port elevation
    portElevs = [307., 323., 336., 349., 362., 401.]
    setFlow = False
    for j, portElev in enumerate(portElevs):
        if abs(elevVal - portElev) < 0.01:
            tcdFlows[j] += remainingFlow
            setFlow = True
    if not setFlow:
        tcdFlows[0] += remainingFlow  # set at lowest layer (flowVal *should* be zero)
    
    resOp = currentRule.getController().getReservoirOp()
    resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

    return
