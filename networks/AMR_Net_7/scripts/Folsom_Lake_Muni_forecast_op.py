from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants
from hec.model import RunTimeStep
from datetime import date

# Script "Global variables"
# Operations
checkOpHour = 12  # Hour to do operations check and move if necessary
startOpDate = date(3000, 3, 1)  # March 1st (move to highest position)
endOpDate = date(3000, 12, 1)  # Dec 1st
maxOpElev = 401.  # maximum allowed elevation (ft)
minOpElev = 331.5  # minimum allowed elevation (ft) (when it is acceptable to go to 317?)
targetTemperature = 18.3333  # deg C (65 deg F)
minDistBlwResSfc = 18.8  # minimum intake distance below reservoir water surface
opInterval = 3.  # interval to move intake down when there is a temp violation
# Variable names
globalVarNameMuniFlow = 'Muni_specified_flow'
globalVarNameMuniElevForecast = 'Muni_elev_forecast'
globalVarNameMuniElevHist = 'Muni_intake_elev'
stateVarNameOpFlag = 'Muni_oper_flag'
# Script constants
temperatureConstitId = 1
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
def checkApplyRule(currentRule, network):
    wqRun = network.getRssRun().getWQRun()
    if not wqRun:
        return False
    rssWQGeometry = wqRun.getRssWQGeometry()
    resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
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

        setMuniOperation(network, currentRule, currentRuntimestep, flowVal, resElev)

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
# Set the forecasted gate elevation
def setMuniElev(network, runtimeStep, elev):
    gv = network.getGlobalVariable(globalVarNameMuniElevForecast)
    if not gv:
        raise NameError("Global variable: " + globalVarNameMuniElevForecast + " not found.")
    gv.setCurrentValue(runtimeStep, elev)


#######################################################################################################
# Get the historical gate elevation
def getMuniElevHist(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameMuniElevHist)
    if not gv:
        raise NameError("Global variable: " + globalVarNameMuniElevHist + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Get the previous shutter elevation
def getPrevElev(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameMuniElevForecast)
    if not gv:
        raise NameError("Global variable: " + globalVarNameMuniElevForecast + " not found.")
    runtimeStepNew = RunTimeStep()
    runtimeStepNew.setStep(max(runtimeStep.getStep()-1, 0))
    return gv.getCurrentValue(runtimeStepNew)


#######################################################################################################
# Set the op flag
def setOpFlag(network, opFlag):
    sv = network.getStateVariable(stateVarNameOpFlag)
    rts = RunTimeStep()
    rts.setStep(1)
    sv.setValue(rts, opFlag)


#######################################################################################################
# Get the op flag
def getOpFlag(network):
    sv = network.getStateVariable(stateVarNameOpFlag)
    if not sv:
        raise NameError("State variable: " + stateVarNameOpFlag + " not found.")
    rts = RunTimeStep()
    rts.setStep(1)
    return sv.getValue(rts)


#######################################################################################################
# Set the TCD operation
def setTCDOperation(network, currentRule, currentRuntimestep, flowVal, withdrawalElev):

    # Fill TCD inlet flow array - only 1 inlet
    tcdFlows = []
    tcdFlows.append(flowVal)
    resOp = currentRule.getController().getReservoirOp()
    resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

    wqRun = network.getRssRun().getWQRun()
    engineAdapter = wqRun.getWqEngineAdapter()
    resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)

    # Reallocate WQCD geometry in WQ Engine
    elevs = [withdrawalElev]
    isRect = [True]
    heights = [0.]
    widths = [0.]
    diameters = [0.]
    releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
    engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, len(elevs), elevs, isRect, heights, widths, diameters)

    # Save to global variable
    setMuniElev(network, currentRuntimestep, withdrawalElev)


#######################################################################################################
# Get a reservoir WQ layer idx for a given elevation
def getLayerForElev(resLayerElevs, elev):
    for k in range(len(resLayerElevs)-1):
        layerBotElev = resLayerElevs[k]
        layerTopElev = resLayerElevs[k+1]
        if (layerBotElev < elev and layerTopElev > elev):
            break
    return k


#######################################################################################################
# Set the operation flag for increasing intake
def setOpFlagCheckMax(network, intakeElev):
    if intakeElev == maxOpElev:
        setOpFlag(network, 1)
    else:
        setOpFlag(network, -1)  # flag to keep near surface until temp violation


#######################################################################################################
# Set the TCD operation
def setMuniOperation(network, currentRule, currentRuntimestep, flowVal, resElev):

    # Change withdrawal elevation based on rules
    wqRun = network.getRssRun().getWQRun()
    engineAdapter = wqRun.getWqEngineAdapter()
    resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
    resLayerElevs = resWQGeoSubdom.getResVerticalLayerBoundaries()
    layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)

    curTime = currentRuntimestep.getHecTime()
    try:
        curDate = date(3000, curTime.month(), curTime.day())
    except ValueError: # Leap year issue
        curDate = date(3000, curTime.month(), curTime.day()-1)
    curHour = curTime.hour()
    iCurStep = currentRuntimestep.getStep()
    insideOpPeriod = curDate >= startOpDate and curDate <= endOpDate

    # First step
    if iCurStep == currentRuntimestep.getRunTimeWindow().getNumLookbackSteps() + 1:
        elev = getMuniElevHist(network, currentRuntimestep)
        if curDate == startOpDate:  # Move up
            elev = resElev - minDistBlwResSfc  # operating constraint
            elev = min(max(minOpElev, elev), maxOpElev)
            setOpFlagCheckMax(network, elev)
        else:
            setOpFlag(network, 1)
    else:
        if curHour != checkOpHour:  # Only check once per day
            elev = getPrevElev(network, currentRuntimestep)
        else:
            if curDate == startOpDate:  # Move up
                elev = resElev - minDistBlwResSfc  # operating constraint
                elev = min(max(minOpElev, elev), maxOpElev)
                setOpFlagCheckMax(network, elev)
            else:
                elev = getPrevElev(network, currentRuntimestep)
                if insideOpPeriod:
                    opFlag = getOpFlag(network)
                    if opFlag < 0:  # check if still moving up
                        if (resElev - elev) > (minDistBlwResSfc + opInterval):
                            elev += opInterval
                            elev = min(max(minOpElev, elev), maxOpElev)
                            setOpFlagCheckMax(network, elev)
                    if elev > resElev - minDistBlwResSfc:
                        elev -= opInterval
                    else:
                        k = getLayerForElev(resLayerElevs, elev)
                        tempForElev = layerTemps[k]
                        if tempForElev > targetTemperature:
                            elev -= opInterval
                            setOpFlag(network, 1)
                    # Otherwise leave as is
            # Otherwise leave as is

    setTCDOperation(network, currentRule, currentRuntimestep, flowVal, elev)
