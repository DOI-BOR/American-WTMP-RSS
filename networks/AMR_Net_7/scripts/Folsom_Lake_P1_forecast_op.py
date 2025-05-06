from hec.model import RunTimeStep
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.rss.model import ReservoirDamElement
from hec.script import Constants
from hec.rss.model.globalvariable import TimeSeriesGlobalVariable, ScalarGlobalVariable
from hec.wqenginecore import WqIoHydroType
from hec.wqenginecore import WQTime
from datetime import date
import math

# Script "Global variables"
# Shutter operations
startOpDate = date(3000, 5, 1)  # May 1st
endOpDate = date(3000, 11, 1)  # Nov 1st
raiseOpDate = date(3000, 3, 1)  # Mar 1st raise shutters to top
useRiverOutletDate = date(3000, 9, 1)  # Sep 1st can use Lower River Outlets
temperatureThreshold = 0.0 #0.75
maxViolationDays = 3 #5
checkOpHour = 12  # Hour to do operations check
debugOutput = False
# Variable names
globalVarNameTotalPenstockFlow = 'Total_Penstock_specified_flow'
globalVarNameShutterElevForecast = 'PX_shutter_elev_forecast'
globalVarNameShutterElevHist = 'PX_shutter_elev'
globalVarNamePSFlow = 'PX_flow_forecast'
globalVarNameRRFlow = 'Lower_RO_flow_forecast'
globalVarNameTempTarget = 'Temperature_Target'
globalVarNameDSControlLoc = 'Downstream_Control_Loc'
globalVarNameEquilibTemp = 'FairOaks_Equilibrium_Temp'
globalVarNameLowerRivFlowHist = 'Lower_Riv_out_flow'
globalVarNameLowerRivFlowForecast = 'Lower_Riv_out_forecast_flow'
globalVarNameLowerRivOutletUse = 'Folsom_Lower_River_use'
globalVarNameLeakage = 'Folsom_leakage'
stateVarNameViolations = 'Temp_Target_Violations'
# Script constants
lastIterationPassNum = 2
lowFlowThreshold = 0.1
temperatureDiffThreshold = 0.1    # avoid dividing by zero when reservoir close to isothermal and need to split flows
# Operation variables
withdrawalPtOffset = 8.9  # in feet - distance to move withdrawal pt above shutter invert
resElevBufr = 27.  # head needed above shutter invert (ft)
maxPenstockFlow = 2889.  # cfs
nMultiShutterDrop = 3

#######################################################################################################
# Gets the allowable shutter elevations - overrides the data in the Reservoir Physical tab
def getShutterElevs():
    elevs = [307., 323., 336., 349., 362., 401.]
    return elevs


#######################################################################################################
# Gets the indexes of the shutter elevations used for forecasting
# 307 = All shutters out
# 336 = Lower shutter in
# 362 = Lower and middle shutters in
# 401 = All shutters in
def getOperableShutterElevIndexes():
    return [0, 2, 4, 5]


#######################################################################################################
# Get the distance downstream for a given temperature control point (in feet)
def getDownstreamDistance(controlPtInt):
    dsDistDict = {1: 71000.,  # Watt Ave Bridge
                  2: 50000.,  # William Pond Park
                  3: 1000.}    # Hazel Ave
    try:
        dist = dsDistDict[controlPtInt]
    except KeyError:
        raise NotImplementedError('Downstream location index ' + str(controlPtInt) + ' not recognized.')
    return dist


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
        
    if evalRule:
        # Get temperature target
        wqTarget = getGVTemperature(network, currentRuntimestep, globalVarNameTempTarget)
        tcdFlows, qPenstock1 = setForecastTCDoperation(currentRule, network, currentRuntimestep, wqTarget, resElev)
    else:
        tcdFlows, qPenstock1 = setDefaultForecastTCDoperation(currentRule, network, currentRuntimestep, resElev)
        
    resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, qPenstock1)
    opValue = OpValue()
    opValue.init(OpRule.RULETYPE_SPEC, qPenstock1)
    return opValue


#######################################################################################################
# Check whether a value is valid
def isValidValue(value, checkZero=True):
    if value is None:
        return False
    elif value == Constants.UNDEFINED_DOUBLE:
        return False
    elif checkZero and value < 0.:
        return False
    else:
        return True


#######################################################################################################
# Get a single river outlet flow for a given time step
def getReleaseInfo(currentRule, network, currentRuntimestep, resElev, usePrevStepAsEstimate):

    # Non-powerhouse outlet names and elevations
    outletDict = {'Service Spillway': 418.,
                  'Auxiliary Spillway': 367.02,
                  'Emergency Spillway': 418.,
                  'Upper River Gates': 280.,
                  'Lower River Gates': 210.}
    powerhouseOutletName = 'Powerhouse'

    resOp = currentRule.getController().getReservoirOp()
    res = resOp.getReservoirElement()

    wqRun = network.getWQRun()
    engineAdapter = wqRun.getWQEngineAdapter()
    rssWQGeometry = wqRun.getRssWQGeometry()
    resWQGeoSubdom = rssWQGeometry.getWQSubdomain(res)
    tempConstit = wqRun.getWQConstituent("Water Temperature")

    # Non-powerhouse flows and temperatures
    qNonPH = 0.
    tempNonPH = 0.
    tempLowRiv = 0.

    for outletName, outletElev in outletDict.items():
        if 'Lower River' in outletName:
            flow = getLowerRiverHistFlow(network, currentRuntimestep)
            # Immediately set the forecast flow (potentially overridden later)
            setLowerRiverForecastFlow(network, currentRuntimestep, flow)
            qLowRiv = flow
        else:
            outletElem = res.getElementByName(outletName)
            roCntrlr = resOp.getControllerForElement(outletElem)
            flow = roCntrlr.getCurMinOpValue(currentRuntimestep).value
            if debugOutput: network.printMessage("Outlet: " + outletName + ", Flow: " + str(flow))
            if not isValidValue(flow) and usePrevStepAsEstimate:
                rts = RunTimeStep()
                rts.setStep(currentRuntimestep.getStep() - 1)
                flow = roCntrlr.getDecisionValue(rts)
            if not isValidValue(flow):
            	flow = 10.  # This is intended to get *some* value if data is missing on the first iteration pass
            	            # It's updated to valid flows during subsequent iteration passes
                #raise ValueError("Invalid value: " + str(flow) + " for " + outletName + " flow for time step: " + str(currentRuntimestep.step))
            qNonPH += flow
            
        if flow > lowFlowThreshold:
            temp = engineAdapter.getWQResultForReleaseAtElev(resWQGeoSubdom, tempConstit, flow, outletElev)
            if temp > 100. or temp < 0.:
                message = "Temperature outside of range (0,100) for flow " + str(flow) + " elevation " + str(outletElev) + " temperature " + str(temp)
                raise ValueError(message)
            if 'Lower River' in outletName:
                tempLowRiv = temp
            else:
                tempNonPH += flow * temp

    if qNonPH > lowFlowThreshold:
        tempNonPH = tempNonPH / qNonPH

    # Powerhouse flow
    qPowerhouse = getTotalPenstockFlow(network, currentRuntimestep)
    if debugOutput: network.printMessage("Outlet: Penstock Total, Flow: " + str(qPowerhouse))

    # Leakage through the powerhouse
    leakageElev = 307.
    lowerMinLeakageFlow = 44. # min cfs
    leakageFraction = getLeakageFractionFromResElev(resElev)
    qLeakage = lowerMinLeakageFlow + leakageFraction*(qPowerhouse-lowerMinLeakageFlow)
    if qLeakage > qPowerhouse:
        qLeakage = qPowerhouse
    qPowerhouse = qPowerhouse - qLeakage
    if qLeakage > lowFlowThreshold:
        tempLeakage = engineAdapter.getWQResultForReleaseAtElev(resWQGeoSubdom, tempConstit, qLeakage, leakageElev)
        if tempLeakage > 100. or tempLeakage < 0.:
            message = "Temperature outside of range (0,100) for flow " + str(qLeakage) + " elevation " + str(leakageElev) + " temperature " + str(tempLeakage)
            raise ValueError(message)
    else:
        tempLeakage = 0.  # not used

    return qPowerhouse, qLowRiv, tempLowRiv, qNonPH, tempNonPH, qLeakage, tempLeakage


#######################################################################################################
# Get the water quality target value by looking for the global variable timeseries
def getGVTemperature(network, currentRuntimestep, gvName):

    globVar = network.getGlobalVariable(gvName)
    if not globVar:
        raise NameError("Global variable: " + gvName + " not found.")

    temp = globVar.getCurrentValue(currentRuntimestep)
    if gvName == globalVarNameEquilibTemp:
        validVal = isValidValue(temp, checkZero=False)
    else:
        validVal = isValidValue(temp, checkZero=True)
    if not validVal:
        raise ValueError("Global variable: " + gvName + " has invalid value " +
                         str(temp) + " for time step: " + str(currentRuntimestep.step))

    # Units conversion
    if type(globVar) is TimeSeriesGlobalVariable:
        tsc = globVar.getTimeSeriesContainer()
        units = tsc.getUnits()
        if 'c' in units.lower():
            convert2C = False
        else:
            convert2C = True
    elif type(globVar) is ScalarGlobalVariable:
        if temp > 32.:
            convert2C = True
        else:
            convert2C = False
    else:
        raise NotImplementedError("Only Scalar and Time Series Global Variable types supported for Temperature Inputs")

    if convert2C:
        tempDegC = (temp - 32.) * 5./9.
    else:
        tempDegC = temp
    return tempDegC


#######################################################################################################
# Get the total penstock flow from a global variable
def getTotalPenstockFlow(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameTotalPenstockFlow)
    if not gv:
        raise NameError("Global variable: " + globalVarNameTotalPenstockFlow + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Set the number of temperature target violations
def setTempTargetViolations(network, numViolations):
    sv = network.getStateVariable(stateVarNameViolations)
    rts = RunTimeStep()
    rts.setStep(1)
    sv.setValue(rts, numViolations)


#######################################################################################################
# Get the number of temperature target violations
def getTempTargetViolations(network):
    sv = network.getStateVariable(stateVarNameViolations)
    if not sv:
        raise NameError("State variable: " + stateVarNameViolations + " not found.")
    rts = RunTimeStep()
    rts.setStep(1)
    return sv.getValue(rts)


#######################################################################################################
# Translate the Folsom reservoir elevation to a leakage fraction (assumed to be at the penstock intake elev)
def getLeakageFractionFromResElev(resElevation):
    if resElevation < 310.0:
        return 0.0
    elif resElevation < 330.0:
        return 0.08
    elif resElevation < 340.0:
        return 0.12
    elif resElevation < 350.0:
        return 0.2
    elif resElevation < 370.0:
        return 0.25
    else:
        return 0.38


#######################################################################################################
# Set the leakage global variable
def setLeakage(network, currentRuntimestep, leakage):
	gv = network.getGlobalVariable(globalVarNameLeakage)
	gv.setCurrentValue(currentRuntimestep, leakage)


#######################################################################################################
# Set the forecasted penstock flow
def setPenstockFlow(network, runtimeStep, flow, psNum):
    gvName = globalVarNamePSFlow.replace('X', str(psNum))
    gv = network.getGlobalVariable(gvName)
    if not gv:
        raise NameError("Global variable: " + gvName + " not found.")
    gv.setCurrentValue(runtimeStep, flow)


#######################################################################################################
# Set the forecasted lower river outlet flow
def setLowerRiverForecastFlow(network, runtimeStep, flow):
    gv = network.getGlobalVariable(globalVarNameLowerRivFlowForecast)
    if not gv:
        raise NameError("Global variable: " + globalVarNameLowerRivFlowForecast + " not found.")
    gv.setCurrentValue(runtimeStep, flow)


#######################################################################################################
# Get the historical river outlet flow
def getLowerRiverHistFlow(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameLowerRivFlowHist)
    if not gv:
        raise NameError("Global variable: " + globalVarNameLowerRivFlowHist + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Set the forecasted gate elevation
def setShutterElev(network, runtimeStep, elev, psNum):
    gvName = globalVarNameShutterElevForecast.replace('X', str(psNum))
    gv = network.getGlobalVariable(gvName)
    if not gv:
        raise NameError("Global variable: " + gvName + " not found.")
    gv.setCurrentValue(runtimeStep, elev)


#######################################################################################################
# Get the historical gate elevation
# TODO: this can be zero, and have to go back in time to get last valid value
# Easier to clean up input time series records to avoid this problem
def getShutterElevHist(network, runtimeStep, psNum):
    gvName = globalVarNameShutterElevHist.replace('X', str(psNum))
    gv = network.getGlobalVariable(gvName)
    if not gv:
        raise NameError("Global variable: " + gvName + " not found.")
    return gv.getCurrentValue(runtimeStep)


#######################################################################################################
# Get the previous shutter elevation
def getPrevShutterElev(network, runtimeStep, psNum):
    gvName = globalVarNameShutterElevForecast.replace('X', str(psNum))
    gv = network.getGlobalVariable(gvName)
    if not gv:
        raise NameError("Global variable: " + gvName + " not found.")
    runtimeStepNew = RunTimeStep()
    runtimeStepNew.setStep(max(runtimeStep.getStep()-1, 0))
    return gv.getCurrentValue(runtimeStepNew)


#######################################################################################################
# Get time series indicating whether or not to use the Lower River Outlets for temperature management
def getUseLowerRiverOutlets(network, runtimeStep):
    gv = network.getGlobalVariable(globalVarNameLowerRivOutletUse)
    if not gv:
        raise NameError("Global variable: " + gvName + " not found.")
    val = gv.getCurrentValue(runtimeStep)
    #network.getRssRun().printMessage(str(val))
    return val > 0.  # value of +1 = use outlets, value of -1 = don't use outlets


#######################################################################################################
# Get next lower shutter elevation
def getLowerShutterLevel(currentElev, opElevs):
    for k in range(len(opElevs)):
        if opElevs[k] == currentElev:
            break
    newk = max(k-1, 0)
    return opElevs[newk]


#######################################################################################################
# Get temperature for an elevation
def getTempForElev(shutterElev, opElevs, shutterLevelTemps):
    k = -1
    for k in range(len(opElevs)):
        if opElevs[k] == shutterElev:
            break
    return shutterLevelTemps[k]


#######################################################################################################
# Get next lower shutter elevation
def getTCDFlowsForShutterElev(psFlow, shutterElev):
    tcdFlows = []
    elevs = getShutterElevs()
    nInletLevels = len(elevs)
    # Initialize flows
    for j in range(nInletLevels):
        if elevs[j] == shutterElev:
            tcdFlows.append(psFlow)
        else:
            tcdFlows.append(0.0)
    return tcdFlows


#######################################################################################################
# Snap a zero or deganged shutter elevation to an allowable one
def snapShutterElev(shutterElev):
    elevs = getShutterElevs()
    opIndexes = getOperableShutterElevIndexes()
    allowedElevs = [elevs[idx] for idx in opIndexes]

    snappedElev = -99
    
    if shutterElev in allowedElevs:
        return shutterElev
    else:
        minDist = 1e6
        for elev in allowedElevs:
            dist = abs(elev - shutterElev)
            if dist < minDist:
                snappedElev = elev
                minDist = dist

        if snappedElev == -99:
        	raise ValueError("snapShutterElev: shutterElev not initialized or not allowed. Check initial shutter elevations. ")
        
        return snappedElev


#######################################################################################################
# Massage historical shutter elevations to something within our forecast operations
def massageHistoricalShutterElev(p1, p2, p3):
    # Move any shutters that aren't on one of our levels (i.e., they are deganged)
    p1new = snapShutterElev(p1)
    p2new = snapShutterElev(p2)
    p3new = snapShutterElev(p3)
    if p1new == p2new and p2new == p3new:
        return [p1new, p2new, p3new]
    else:
        # Multiple levels
        if p1new == p2new or p1new == p3new or p2new == p3new:  # 2 levels
            lowerElev = min(p1new, p2new, p3new)
            upperElev = max(p1new, p2new, p3new)
            twoHighOneLow = [lowerElev, upperElev, upperElev]
            oneHighTwoLow = [lowerElev, lowerElev, upperElev]
            if p2new == p3new:  # p1 is alone
                if p1new == lowerElev:
                    return twoHighOneLow
                else:
                    return oneHighTwoLow
            elif p1new == p3new:  # p2 is alone
                if p2new == lowerElev:
                    return twoHighOneLow
                else:
                    return oneHighTwoLow
            else:  # p3 is alone
                if p3new == lowerElev:
                    return twoHighOneLow
                else:
                    return oneHighTwoLow

        else:  # gates open on 3 levels - not supported yet
            raise ValueError("Historical gate operations not supported - P1 elev: " + str(p1new) + " P2 elev: " + str(p2new) + " P3 elev: " + str(p3new))


#######################################################################################################
# Modify the temperature target for non-powerhouse downstream flows
def modifyTempTarget(qPH, qNonPH, tempNonPH, qLeakage, tempLeakage, wqTarget):
    qSum = qPH + qNonPH + qLeakage
    wqTargetNew = wqTarget * qSum / qPH - tempNonPH * qNonPH / qPH - tempLeakage * qLeakage / qPH
    return wqTargetNew


#######################################################################################################
# Split penstock flow evenly
def splitFlowEvenly(totalPSFlow):
    if debugOutput: network.printMessage("Splitting flow evenly")
    avgFlow = totalPSFlow / 3.
    return [avgFlow, avgFlow, avgFlow]


#######################################################################################################
# Try to put all penstock flow through lower penstock(s)
def putFlowLowest(totalPSFlow, p1Elev, p2Elev, p3Elev):
    if debugOutput: network.printMessage("Putting flow lowest")
    if p1Elev == p2Elev:
        avgFlow = totalPSFlow / 2.
        if avgFlow > maxPenstockFlow:
            p1Flow = maxPenstockFlow
            p2Flow = maxPenstockFlow
            p3Flow = totalPSFlow - 2 * maxPenstockFlow
        else:
            p1Flow = avgFlow
            p2Flow = avgFlow
            p3Flow = 0.
    else:
        p1Flow = min(totalPSFlow, maxPenstockFlow)
        avgFlow = (totalPSFlow - p1Flow) / 2.
        p2Flow = avgFlow
        p3Flow = avgFlow
    return [p1Flow, p2Flow, p3Flow]


#######################################################################################################
# Try to put all penstock flow through upper penstock(s)
def putFlowHighest(totalPSFlow, p1Elev, p2Elev, p3Elev):
    if debugOutput: network.printMessage("Putting flow highest")
    if p1Elev == p2Elev:
        p3Flow = min(totalPSFlow, maxPenstockFlow)
        avgFlow = (totalPSFlow - p3Flow) / 2.
        p1Flow = avgFlow
        p2Flow = avgFlow
    else:
        avgFlow = totalPSFlow / 2.
        if avgFlow > maxPenstockFlow:
            p2Flow = maxPenstockFlow
            p3Flow = maxPenstockFlow
            p1Flow = totalPSFlow - 2 * maxPenstockFlow
        else:
            p2Flow = avgFlow
            p3Flow = avgFlow
            p1Flow = 0.
    return [p1Flow, p2Flow, p3Flow]


#######################################################################################################
# Try to put all penstock flow through upper penstock(s)
def splitFlow(totalPSFlow, lowerFlow, p1Elev, p2Elev, p3Elev):
    if debugOutput: network.printMessage("Splitting flow based on temperature")
    upperFlow = totalPSFlow - lowerFlow
    if p1Elev == p2Elev:
        if upperFlow > maxPenstockFlow:
            p3Flow = maxPenstockFlow
            avgFlow = (lowerFlow + upperFlow - maxPenstockFlow) / 2.
            p1Flow = avgFlow
            p2Flow = avgFlow
        else:
            avgFlow = lowerFlow / 2.
            if avgFlow > maxPenstockFlow:
                p1Flow = maxPenstockFlow
                p2Flow = maxPenstockFlow
                p3Flow = upperFlow + (lowerFlow - 2 * maxPenstockFlow)
            else:
                p1Flow = avgFlow
                p2Flow = avgFlow
                p3Flow = upperFlow
    else:
        if lowerFlow > maxPenstockFlow:
            p1Flow = maxPenstockFlow
            avgFlow = (upperFlow + lowerFlow - maxPenstockFlow) / 2.
            p2Flow = avgFlow
            p3Flow = avgFlow
        else:
            avgFlow = upperFlow / 2.
            if avgFlow > maxPenstockFlow:
                p2Flow = maxPenstockFlow
                p3Flow = maxPenstockFlow
                p1Flow = lowerFlow + (upperFlow - 2 * maxPenstockFlow)
            else:
                p2Flow = avgFlow
                p3Flow = avgFlow
                p1Flow = lowerFlow
    return [p1Flow, p2Flow, p3Flow]


#######################################################################################################
# Calculate flow through each penstocks with a fixed shutter operation
def operateForFixedShutters(totalPSFlow, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps):
    if debugOutput: network.printMessage("Operating For Fixed Shutter Elevations")
    if p1Elev == p2Elev and p2Elev == p3Elev:
        [p1Flow, p2Flow, p3Flow] = splitFlowEvenly(totalPSFlow)
    else:
        t1 = getTempForElev(p1Elev, opElevs, shutterLevelTemps)
        t3 = getTempForElev(p3Elev, opElevs, shutterLevelTemps)
        if t3 - t1 < temperatureDiffThreshold:
            [p1Flow, p2Flow, p3Flow] = splitFlowEvenly(totalPSFlow)
        else:
            if wqTarget < t1:
                [p1Flow, p2Flow, p3Flow] = putFlowLowest(totalPSFlow, p1Elev, p2Elev, p3Elev)
            elif wqTarget > t3:
                [p1Flow, p2Flow, p3Flow] = putFlowHighest(totalPSFlow, p1Elev, p2Elev, p3Elev)
            else:
                lowerFlow = totalPSFlow * (wqTarget - t3) / (t1 - t3)
                [p1Flow, p2Flow, p3Flow] = splitFlow(totalPSFlow, lowerFlow, p1Elev, p2Elev, p3Elev)
    return [p1Flow, p2Flow, p3Flow]


#######################################################################################################
# Calculate outlet temperature
def calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps):
    t1 = getTempForElev(p1Elev, opElevs, shutterLevelTemps)
    t2 = getTempForElev(p2Elev, opElevs, shutterLevelTemps)
    t3 = getTempForElev(p3Elev, opElevs, shutterLevelTemps)
    psSum = p1Flow + p2Flow + p3Flow
    outletTemp = (t1 * p1Flow + t2 * p2Flow + t3 * p3Flow) / psSum
    return outletTemp


#######################################################################################################
# Return highest available shutter level for a reservoir elevation
def getHighestLevel(network, resElev, opElevs):
    highestLevel = opElevs[0]
    for k in range(1, len(opElevs)):
        if resElev > opElevs[k] + resElevBufr:
            highestLevel = opElevs[k]
        else:
            break
    return highestLevel


#######################################################################################################
# Get next lower set of shutter elevations
def getLowerShutterSet(p1CurElev, p2CurElev, p3CurElev, opElevs):
    if p1CurElev == p2CurElev and p2CurElev == p3CurElev:
        if p1CurElev == opElevs[0]:
            # Can't do anything
            p1NewElev = p1CurElev
            p2NewElev = p2CurElev
            p3NewElev = p3CurElev
        else:
            # Move shutter 1 down
            p1NewElev = getLowerShutterLevel(p1CurElev, opElevs)
            p2NewElev = p2CurElev
            p3NewElev = p3CurElev
    elif p2CurElev == p3CurElev:
        # Move shutter 2 down
        p1NewElev = p1CurElev
        p2NewElev = getLowerShutterLevel(p2CurElev, opElevs)
        p3NewElev = p3CurElev
    else:
        # Move shutter 3 down
        p1NewElev = p1CurElev
        p2NewElev = p2CurElev
        p3NewElev = getLowerShutterLevel(p3CurElev, opElevs)
    return [p1NewElev, p2NewElev, p3NewElev]


#######################################################################################################
# Get low flow split
def getLowFlowSplit(totalPSFlow):
    return [totalPSFlow, 0., 0.]


#######################################################################################################
# Calculate lower river - penstock flow split
def splitFlowLowRiver(qPowerhouse, qLeakage, psTemp, roTemp, backRoutedWqTarget, tempLeakage):
    if psTemp - roTemp < temperatureDiffThreshold:
        # Penstocks and lower river are the same temperature
        # Put all through the penstocks (assume late in season and not limited by ps max capacity)
        [p1Flow, p2Flow, p3Flow] = splitFlowEvenly(qPowerhouse)
        qLowRiver = 0.
    else:
        qPHAll = qPowerhouse + qLeakage
        # Modify the temp at the dam to account for ps leakage
        wqTargetNew = backRoutedWqTarget * qPHAll / qPowerhouse - tempLeakage * qLeakage / qPowerhouse
        if debugOutput: network.printMessage('Modified temp for lower river outlet calc: ' + str(wqTargetNew))
        qLowRiver = qPowerhouse * (wqTargetNew - psTemp) / (roTemp - psTemp)
        qLowRiver = min(qPowerhouse, max(qLowRiver, 0))  # clip
        qPH = qPowerhouse - qLowRiver
        [p1Flow, p2Flow, p3Flow] = splitFlowEvenly(qPH)
        
    return [p1Flow, p2Flow, p3Flow, qLowRiver]


#######################################################################################################
#def getDSControlLoc(network):
#    gv = network.getGlobalVariable(globalVarNameDSControlLoc)
#    if not gv:
#        raise NameError("Global variable: " + globalVarNameDSControlLoc + " not found.")
#    return gv.getValue()

def getDSControlLoc(network,currentRuntimestep):
    gv = network.getGlobalVariable(globalVarNameDSControlLoc)

    fail=False
    if not gv:
        fail = True
    else:
        loc = gv.getValue()
        if loc is None:
            fail = True
        elif loc < 0 or loc > 3:
            fail = True

    if fail:
        raise NameError("Global variable: " + globalVarNameDSControlLoc + " not found or invalid.")
        #if currentRuntimestep.getStep() < 2:        
        #	network.getRssRun().printWarningMessage("Warning: Forecast_TCS script can't understand downstream control loc " +
        #                                        globalVarNameDSControlLoc +". Assuming default of 'Watt Ave Br'.")
        #return 1
    else:
    	return loc


#######################################################################################################
def getNatomaOutflow(network, currentRuntimestep, usePrevStepAsEstimate=True):

    natomaName = "Lake Natoma"
    natElem = network.findElement(natomaName)
    if not natElem:
        raise NameError("Network element: " + natomaName + " not found.")
    natOpSet = natElem.getReservoirOp()
    rde = ReservoirDamElement()
    childElemVec = natElem.getElementsByClass(type(rde), None)
    cntrlr = natOpSet.getControllerForElement(childElemVec[0])
    flow = cntrlr.getCurMinOpValue(currentRuntimestep).value
    if (not isValidValue(flow) or flow < lowFlowThreshold) and usePrevStepAsEstimate:
        rts = RunTimeStep()
        rts.setStep(currentRuntimestep.getStep() - 1)
        flow = cntrlr.getDecisionValue(rts)
    if not isValidValue(flow):
        raise ValueError("Invalid value: " + str(flow) + " for " + natomaName + " flow for time step: " + str(currentRuntimestep.step))

    return flow


#######################################################################################################
def getNatomaAvgTemp(network):

    natomaName = "Lake Natoma"
    natElem = network.findElement(natomaName)
    if not natElem:
        raise NameError("Network element: " + natomaName + " not found.")

    wqRun = network.getRssRun().getWQRun()
    rssWQGeometry = wqRun.getRssWQGeometry()
    resWQGeoSubdom = rssWQGeometry.getWQSubdomain(natElem)
    engineAdapter = wqRun.getWQEngineAdapter()
    layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)
    nLayers = len(layerTemps)
    layerVols = engineAdapter.getHydroResult(resWQGeoSubdom.getId(), WqIoHydroType.CELL_VOLUME.id,
                                             WQTime.TIME_STEP_INFO.END_OF_STEP.id, nLayers)
    avgTemp = 0.
    totalVol = 0.
    for j in range(nLayers):
        avgTemp += layerTemps[j] * layerVols[j]
        totalVol += layerVols[j]
    return avgTemp / totalVol


#######################################################################################################
# Backcalculate the temperature required at Folsom Dam from the downstream temperature target
def backRouteWQTarget(network, currentRuntimestep, totalFolsomRelease):

    # Get the downstream control location
    loc = getDSControlLoc(network,currentRuntimestep)
    downstreamDistance = getDownstreamDistance(loc)

    # Constants for heat exchange during routing
    Kcoef = 1.1  # velocity as a function of flow
    alpha = 0.47  # velocity as a function of flow
    natConPoolVol = 8000. * 43560.  # cubic feet, assumed this is top of conservation
    multiplier = 24.  # Inflow more important than CSTR assumption because of where inflow enters vertically
    exchCoef = 0.0135  # exchange rate between atmosphere and river temp - original, may-Oct
    #exchCoef = 0.0128  # exchange rate between atmosphere and river temp - original, jul-sep


    # Power law approximation for velocity in the Sacramento River
    natomaFlow = getNatomaOutflow(network, currentRuntimestep)
    if debugOutput: network.printMessage('Natoma outflow: ' + str(natomaFlow))
    velocity = Kcoef * (totalFolsomRelease / 1000)**alpha  # power law approximation
    
    # Calculate travel time in model steps
    travTime = downstreamDistance / velocity
    deltaT = currentRuntimestep.getTimeStepSeconds()
    travTimeSteps = int(round(travTime / deltaT))
    if debugOutput: network.printMessage('Travel time steps: ' + str(travTimeSteps))

    futureRts = RunTimeStep()
    futureRts.setStep(min(currentRuntimestep.getStep() + travTimeSteps, currentRuntimestep.getTotalNumSteps()-1))
    targetTempFuture = getGVTemperature(network, futureRts, globalVarNameTempTarget)

    # Get Natoma pool information
    flowVol = totalFolsomRelease * deltaT
    natFraction = flowVol / natConPoolVol
    natFraction = min(natFraction * multiplier, 0.5) # max replacement fraction is 1/2 of natoma per day ... is always heats/cools some 
    natomaResAvgTemp = getNatomaAvgTemp(network)
    #tSearchMin = 5.  # min temp (deg C) to search for outflow temp from Shasta to meet DS target
    #tSearchMax = 25.
    tSearchMin = natomaResAvgTemp - 4.
    tSearchMax = natomaResAvgTemp + 2.
    numIters = 21
    bracketed = False
    cantBeMet = False
    for j in range(numIters):
        outletTemp = tSearchMin + float(j) / float(numIters+1) * (tSearchMax - tSearchMin)
        # Impact of Natoma
        t = (1 - natFraction) * natomaResAvgTemp + natFraction * outletTemp
        if debugOutput: network.printMessage('Outlet temp, info: ' + str(outletTemp) + ', ' + str(natFraction) + ', ' + str(natomaResAvgTemp))
        # Route downstream
        deltaTempStr = str(t) + ','
        for k in range(travTimeSteps):
            futureRts.setStep(min(currentRuntimestep.getStep() + k,currentRuntimestep.getTotalNumSteps()-1))
            eqTemp = getGVTemperature(network, futureRts, globalVarNameEquilibTemp)
            deltaTemp = (eqTemp - t) * exchCoef
            t += deltaTemp
            deltaTempStr += str(t) + ','
        if debugOutput: network.printMessage('Delta T info: ' + deltaTempStr)
        if j == 0:
            prevT = t
            prevOutletT = outletTemp
        if t > targetTempFuture > prevT:
            upperOutletT = outletTemp
            upperT = t
            lowerOutletT = prevOutletT
            lowerT = prevT
            bracketed = True
            break
        elif prevT > targetTempFuture > t:
            lowerOutletT = outletTemp
            lowerT = t
            upperOutletT = prevOutletT
            upperT = prevT
            bracketed = True
            break
        elif j == 0 and t > targetTempFuture:
            cantBeMet = True
            break
        prevT = t
        prevOutletT = outletTemp

    if bracketed:
        # Linear interpolation
        targetTemp = (upperT - targetTempFuture) / (upperT - lowerT) * (upperOutletT - lowerOutletT) + lowerOutletT
    elif cantBeMet:
        targetTemp = outletTemp
    else:
        if t < targetTempFuture:
            targetTemp = outletTemp
        else:
            network.printMessage('Target Temperature Downstream' + str(targetTempFuture))
            raise ValueError('Outlet temperature not bracketed')

    return targetTemp


#######################################################################################################
# Set the TCD operation for first passes through the rule stack when WQ is not being evaluated
def setDefaultForecastTCDoperation(currentRule, network, currentRuntimestep, resElev):

    qPowerhouse, qLowRiv, tempLowRiv, qOtherNonPH, tempOtherNonPH, qLeakage, tempLeakage = getReleaseInfo(currentRule, network, currentRuntimestep, resElev, True)
    [p1Flow, p2Flow, p3Flow] = splitFlowEvenly(qPowerhouse)
    setLowerRiverForecastFlow(network, currentRuntimestep, qLowRiv)

    setPenstockFlow(network, currentRuntimestep, p1Flow, 1)
    setPenstockFlow(network, currentRuntimestep, p2Flow, 2)
    setPenstockFlow(network, currentRuntimestep, p3Flow, 3)

    elevs = getShutterElevs()
    opIndexes = getOperableShutterElevIndexes()
    allowedElevs = [elevs[idx] for idx in opIndexes]
    p1Elev = allowedElevs[0]
    p2Elev = p1Elev
    p3Elev = p1Elev
    setShutterElev(network, currentRuntimestep, p1Elev, 1)
    setShutterElev(network, currentRuntimestep, p2Elev, 2)
    setShutterElev(network, currentRuntimestep, p3Elev, 3)

    tcdFlows = getTCDFlowsForShutterElev(p1Flow, p1Elev)
    tcdFlows[0] += qLeakage
    totalP1flow = p1Flow + qLeakage

    return tcdFlows, totalP1flow
    

#######################################################################################################
# Set the TCD operation for a forecast
def setForecastTCDoperation(currentRule, network, currentRuntimestep, wqTarget, resElev):

    curTime = currentRuntimestep.getHecTime()
    try:
        curDate = date(3000, curTime.month(), curTime.day())
    except ValueError: # Leap year issue
        curDate = date(3000, curTime.month(), curTime.day()-1)
    curHour = curTime.hour()
    insideOpPeriod = startOpDate <= curDate <= endOpDate
    iCurStep = currentRuntimestep.getStep()

    if debugOutput: network.printMessage("**************************************************************************************")
    if debugOutput: network.printMessage(curTime.toString())

    # Get flow and temperature information
    # Flows broken down into powerhouse and non powerhouse
    # Temperature estimate for the non powerhouse releases
    qPowerhouse, qLowRiv, tempLowRiv, qOtherNonPH, tempOtherNonPH, qLeakage, tempLeakage = getReleaseInfo(currentRule, network, currentRuntimestep, resElev, True)
    setLeakage(network, currentRuntimestep, qLeakage)
    useLowerRiverOutlets_value = getUseLowerRiverOutlets(network, currentRuntimestep)
    useLowerRiverOutlets = useLowerRiverOutlets_value > 0.
    #network.printMessage("Use lower river outlets: " + str(useLowerRiverOutlets) + " " + str(useLowerRiverOutlets_value))
    #if curDate < useRiverOutletDate:
    if not useLowerRiverOutlets:
        qNonPH = qLowRiv + qOtherNonPH
        if qNonPH > lowFlowThreshold:
            tempNonPH = (qLowRiv * tempLowRiv + qOtherNonPH * tempOtherNonPH) / qNonPH
        else:
            tempNonPH = 0.
    else:  # incorporate historical lower river flow into penstock flow for predictive purposes
        qNonPH = qOtherNonPH
        tempNonPH = tempOtherNonPH
        qPowerhouse = qPowerhouse + qLowRiv
        setLowerRiverForecastFlow(network, currentRuntimestep, 0.)
    if debugOutput: network.printMessage("Flows (PH, nonPH, leak): " + str(qPowerhouse) + ", " + str(qNonPH) + ", " + str(qLeakage))
    if debugOutput: network.printMessage("Temps (nonPH, leak): " + str(tempNonPH) + ", " + str(tempLeakage))

    # Route target temperature back from downstream location
    totalFolsomRelease = qPowerhouse + qNonPH + qLeakage
    if debugOutput: network.printMessage("Temperature target downstream: " + str(wqTarget))
    if debugOutput: network.printMessage("Total Folsom release: " + str(totalFolsomRelease))
    backRoutedWqTarget = backRouteWQTarget(network, currentRuntimestep, totalFolsomRelease)
    if debugOutput: network.printMessage("Temperature target at Folsom Dam: " + str(backRoutedWqTarget))
    wqTarget = backRoutedWqTarget

    # Get temperature target modified for leakage and non powerhouse releases
    if qPowerhouse > lowFlowThreshold:
        wqTarget = modifyTempTarget(qPowerhouse, qNonPH, tempNonPH, qLeakage, tempLeakage, wqTarget)
    if debugOutput: network.printMessage("Modified temperature target: " + str(wqTarget))

    # Get temperatures at shutter elevations
    elevs = getShutterElevs()
    opIndexes = getOperableShutterElevIndexes()
    opElevs = [elevs[idx] for idx in opIndexes]
    wqRun = network.getWQRun()
    engineAdapter = wqRun.getWQEngineAdapter()
    rssWQGeometry = wqRun.getRssWQGeometry()
    resOp = currentRule.getController().getReservoirOp()
    res = resOp.getReservoirElement()
    resWQGeoSubdom = rssWQGeometry.getWQSubdomain(res)

    resLayerElevs = resWQGeoSubdom.getResLayerBoundaryElevs()
    numLayers = len(resLayerElevs)-1
    layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)
    shutterLevelTemps = []
    for idx in opIndexes:
        if idx == 0:
            withdrawalElev = elevs[idx]
        else:
            withdrawalElev = elevs[idx] + withdrawalPtOffset
        for k in range(numLayers):
            layerBotElev = resLayerElevs[k]
            layerTopElev = resLayerElevs[k+1]
            if layerBotElev < withdrawalElev < layerTopElev:
                shutterLevelTemps.append(layerTemps[k])
                break
    if debugOutput: network.printMessage("Shutter level temperatures: " + str(shutterLevelTemps))
    riverOutletElev = 210.
    for k in range(numLayers):
        layerBotElev = resLayerElevs[k]
        layerTopElev = resLayerElevs[k+1]
        if layerBotElev < riverOutletElev < layerTopElev:
            riverOutletTemp = layerTemps[k]
            break
    if debugOutput: network.printMessage("River outlet temperature: " + str(riverOutletTemp))

    highestLevel = getHighestLevel(network, resElev, opElevs)
    numViolations = getTempTargetViolations(network)
    if debugOutput: network.printMessage("Reservoir Elevation: " + str(resElev))
    if debugOutput: network.printMessage("Highest allowable shutter elevation: " + str(highestLevel))
    if debugOutput: network.printMessage("Current number of violations: " + str(numViolations))

    # First time step
    if iCurStep == currentRuntimestep.getRunTimeWindow().getNumLookbackSteps() + 1:
        p1 = getShutterElevHist(network, currentRuntimestep, 1)
        p2 = getShutterElevHist(network, currentRuntimestep, 2)
        p3 = getShutterElevHist(network, currentRuntimestep, 3)

        if debugOutput: network.printMessage("First time step")
        if debugOutput: network.printMessage("Hist shutter elevations: " + str(p1) + ", " + str(p2) + ", " + str(p3))

        # Need to massage to levels that are operable for our logic
        [p1Elev, p2Elev, p3Elev] = massageHistoricalShutterElev(p1, p2, p3)
        if debugOutput: network.printMessage("Massaged shutter elevations: " + str(p1Elev) + ", " + str(p2Elev) + ", " + str(p3Elev))

        # Move down if historical logs not consistent with reservoir elevation
        if p1Elev > resElev + resElevBufr:
            p1Elev = getLowerShutterLevel(p1Elev, opElevs)
            if debugOutput: network.printMessage("Lowering shutter 1 for res elevation constraint")
        if p2Elev > resElev + resElevBufr:
            p2Elev = getLowerShutterLevel(p2Elev, opElevs)
            if debugOutput: network.printMessage("Lowering shutter 2 for res elevation constraint")
        if p3Elev > resElev + resElevBufr:
            p3Elev = getLowerShutterLevel(p3Elev, opElevs)
            if debugOutput: network.printMessage("Lowering shutter 3 for res elevation constraint")

        # ... And move up if the first time step happens to be the start of the operation period
        if curDate == raiseOpDate:  # raise shutters to highest position
            if debugOutput: network.printMessage("Raising all shutters to highest allowable level")
            p1Elev = highestLevel
            p2Elev = highestLevel
            p3Elev = highestLevel
            setTempTargetViolations(network, -1)  # flag to keep raising if necessary

        if qPowerhouse > lowFlowThreshold:
            [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)
            if debugOutput: network.printMessage("Operating for fixed shutter positions")

            # Check outlet temperature
            outletTemp = calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps)
            if outletTemp > wqTarget + temperatureThreshold:
                if insideOpPeriod:
                    if debugOutput: network.printMessage("Setting num violations = 1")
                    setTempTargetViolations(network, 1)
                else:
                    if debugOutput: network.printMessage("Setting num violations = -1")
                    setTempTargetViolations(network, -1)
            else:  # Flag to keep raising gates if temperature target being met
                if debugOutput: network.printMessage("Setting num violations = -1")
                setTempTargetViolations(network, -1)
        else:
            [p1Flow, p2Flow, p3Flow] = getLowFlowSplit(qPowerhouse)

    else:
        # Start with previous shutter elevations
        p1Elev = getPrevShutterElev(network, currentRuntimestep, 1)
        p2Elev = getPrevShutterElev(network, currentRuntimestep, 2)
        p3Elev = getPrevShutterElev(network, currentRuntimestep, 3)
        if debugOutput: network.printMessage("Previous step shutter elevations: " + str(p1Elev) + ", " + str(p2Elev) + ", " + str(p3Elev))

        if curHour == checkOpHour:
            if not insideOpPeriod:

                if debugOutput: network.printMessage("Not within operation period")

                # Operate for elevation
                if curDate == raiseOpDate:  # raise shutters to highest position
                    if debugOutput: network.printMessage("Raising all shutters to highest allowable level")
                    p1Elev = highestLevel
                    p2Elev = highestLevel
                    p3Elev = highestLevel
                    if debugOutput: network.printMessage("Setting num violations = -1")
                    setTempTargetViolations(network, -1)  # flag to keep raising if necessary

                # Operate for elevation
                if p1Elev > resElev + resElevBufr:
                    p1Elev = getLowerShutterLevel(p1Elev, opElevs)
                    if debugOutput: network.printMessage("Lowering shutter 1 for res elevation constraint")
                if p2Elev > resElev + resElevBufr:
                    p2Elev = getLowerShutterLevel(p2Elev, opElevs)
                    if debugOutput: network.printMessage("Lowering shutter 2 for res elevation constraint")
                if p3Elev > resElev + resElevBufr:
                    p3Elev = getLowerShutterLevel(p3Elev, opElevs)
                    if debugOutput: network.printMessage("Lowering shutter 3 for res elevation constraint")

                if raiseOpDate <= curDate <= startOpDate:
                    if highestLevel > p1Elev:
                        if debugOutput: network.printMessage("Can raise gates for res elevation rule")
                        numViolations = numViolations - 1
                        setTempTargetViolations(network, numViolations)
                    else:
                        setTempTargetViolations(network, -1)  # reset
                    if numViolations < -3:  # raise shutters
                        if debugOutput: network.printMessage("Raising all gates for res elevation rule")
                        p1Elev = highestLevel
                        p2Elev = highestLevel
                        p3Elev = highestLevel
                        setTempTargetViolations(network, -1)

                if qPowerhouse > lowFlowThreshold:
                    if numViolations > 0 and p1Elev == opElevs[0] and p3Elev == opElevs[0] and useLowerRiverOutlets: #curDate > useRiverOutletDate:
                        if debugOutput: network.printMessage("Using river outlets")
                        # Need to use river outlets
                        psTemp = shutterLevelTemps[0]
                        roTemp = riverOutletTemp
                        [p1Flow, p2Flow, p3Flow, qLowRiver] = splitFlowLowRiver(qPowerhouse, qLeakage, psTemp, roTemp, backRoutedWqTarget, tempLeakage)
                        setLowerRiverForecastFlow(network, currentRuntimestep, qLowRiver)
                        qPowerhouse = p1Flow + p2Flow + p3Flow
                        if debugOutput: network.printMessage("Penstock flows: " + str(qPowerhouse) + ", River outlet flows: " + str(qLowRiver))
                    else:
                        [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)
                else:
                    [p1Flow, p2Flow, p3Flow] = getLowFlowSplit(qPowerhouse)
                
            else:

                if debugOutput: network.printMessage("Within operation period")

                # Operate for elevation
                if curDate == raiseOpDate:  # raise shutters to highest position
                    if debugOutput: network.printMessage("Raising all shutters to highest allowable level")
                    p1Elev = highestLevel
                    p2Elev = highestLevel
                    p3Elev = highestLevel
                    if debugOutput: network.printMessage("Setting num violations = -1")
                    setTempTargetViolations(network, -1)  # flag to keep raising if necessary
				

                numViolations = getTempTargetViolations(network)
                if numViolations < 0:  # still in raising period
                    if highestLevel > p1Elev:
                        if debugOutput: network.printMessage("Can raise gates for res elevation rule")
                        numViolations = numViolations - 1
                        setTempTargetViolations(network, numViolations)
                    else:
                        setTempTargetViolations(network, -1)  # reset
                    if numViolations < -3:  # raise shutters
                        if debugOutput: network.printMessage("Raising all gates for res elevation rule")
                        p1Elev = highestLevel
                        p2Elev = highestLevel
                        p3Elev = highestLevel
                        setTempTargetViolations(network, -1)

                # lower shutters if necessary
                lowered = False
                if highestLevel < p1Elev:
                    p1Elev = highestLevel
                    if debugOutput: network.printMessage("Lowering shutter 1 for res elevation constraint")
                    lowered = True
                if highestLevel < p2Elev:
                    p2Elev = highestLevel
                    if debugOutput: network.printMessage("Lowering shutter 2 for res elevation constraint")
                    lowered = True
                if highestLevel < p3Elev:
                    p3Elev = highestLevel
                    if debugOutput: network.printMessage("Lowering shutter 3 for res elevation constraint")
                    lowered = True
                if lowered:
                    if numViolations < 0:  # temperature violations haven't come into play yet
                        setTempTargetViolations(network, -1)
                        if debugOutput: network.printMessage("Setting num violations = -1")
                    else:
                        setTempTargetViolations(network, 0)
                        if debugOutput: network.printMessage("Setting num violations = 0")

                if qPowerhouse > lowFlowThreshold:
                    # Check temperatures
                    [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)
                    outletTemp = calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps)
                    if debugOutput: network.printMessage("Avg penstock temp after res elevation rules: " + str(outletTemp))

                    if outletTemp > wqTarget + temperatureThreshold:
                        if debugOutput: network.printMessage("Temperature exceeds target")
                        if numViolations < 0:
                            if debugOutput: network.printMessage("Setting num violations = 1")
                            setTempTargetViolations(network, 1)
                        else:
                            numViolations += 1
                            if debugOutput: network.printMessage("Setting num violations = " + str(numViolations))
                            setTempTargetViolations(network, numViolations)

                    if numViolations > maxViolationDays:  # now do something about it
                        if p1Elev == opElevs[0] and p3Elev == opElevs[0] and useLowerRiverOutlets: #curDate > useRiverOutletDate:
                            # Need to use river outlets
                            if debugOutput: network.printMessage("Using river outlets")
                            psTemp = shutterLevelTemps[0]
                            roTemp = riverOutletTemp
                            [p1Flow, p2Flow, p3Flow, qLowRiver] = splitFlowLowRiver(qPowerhouse, qLeakage, psTemp, roTemp, backRoutedWqTarget, tempLeakage)
                            setLowerRiverForecastFlow(network, currentRuntimestep, qLowRiver)
                            qPowerhouse = p1Flow + p2Flow + p3Flow
                            if debugOutput: network.printMessage("Penstock flows: " + str(qPowerhouse) + ", River outlet flows: " + str(qLowRiver))
                        else:
                            [p1Elev, p2Elev, p3Elev] = getLowerShutterSet(p1Elev, p2Elev, p3Elev, opElevs)
                            if debugOutput: network.printMessage("Moving to next lower shutter elevation set")
                            if debugOutput: network.printMessage("New shutter elevations: " + str(p1Elev) + ", " + str(p2Elev) + ", " + str(p3Elev))

                            # Added 2025-04, B. Saenz - check and drop up to 3 shutters
                            # TODO: if we retain this block, code can be optimized a bit
                            #for nmsd in range(nMultiShutterDrop-1):
	                        #    [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)														
	                        #    outletTemp = calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps)
	                        #    if outletTemp > wqTarget + temperatureThreshold:
	                        #    	if debugOutput: network.printMessage("Temperature exceeds target, dropping another shutter: " + str(outletTemp))
	                        #    	[p1Elev, p2Elev, p3Elev] = getLowerShutterSet(p1Elev, p2Elev, p3Elev, opElevs)
	                        #    	if debugOutput: network.printMessage("Moving to next lower shutter elevation set")
	                        #    	if debugOutput: network.printMessage("New shutter elevations: " + str(p1Elev) + ", " + str(p2Elev) + ", " + str(p3Elev))

							# Check temperatures
                            [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)
                            outletTemp = calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps)
                            if debugOutput: network.printMessage("Avg penstock temp after operations change: " + str(outletTemp))
                            if outletTemp > wqTarget + temperatureThreshold:
                                if debugOutput: network.printMessage("Temperature exceeds target")
                                if debugOutput: network.printMessage("Setting num violations = 1")
                                setTempTargetViolations(network, 1)
                            else:
                                if debugOutput: network.printMessage("Setting num violations = 0")
                                setTempTargetViolations(network, 0)
                else:
                    [p1Flow, p2Flow, p3Flow] = getLowFlowSplit(qPowerhouse)

                # Yank all shutters at op end (typically Nov. 1)
                if curDate == endOpDate:  # raise shutters to highest position
                    if debugOutput: network.printMessage("Lowering all shutters to lowest level")
                    p1Elev = opElevs[0]
                    p2Elev = opElevs[0]
                    p3Elev = opElevs[0]
                    if debugOutput: network.printMessage("Setting num violations = -1")
                    setTempTargetViolations(network, -1)  # flag to keep raising if necessary

        else:
            # Keep current gate elevations
            if debugOutput: network.printMessage("Current hour not used for checking operations. Operating for fixed shutter elevations")
            if p1Elev == opElevs[0] and p3Elev == opElevs[0] and useLowerRiverOutlets: #curDate > useRiverOutletDate
                if debugOutput: network.printMessage("Using river outlets")
                # Need to use river outlets
                psTemp = shutterLevelTemps[0]
                roTemp = riverOutletTemp
                [p1Flow, p2Flow, p3Flow, qLowRiver] = splitFlowLowRiver(qPowerhouse, qLeakage, psTemp, roTemp, backRoutedWqTarget, tempLeakage)
                setLowerRiverForecastFlow(network, currentRuntimestep, qLowRiver)
                qPowerhouse = p1Flow + p2Flow + p3Flow
                if debugOutput: network.printMessage("Penstock flows: " + str(qPowerhouse) + ", River outlet flows: " + str(qLowRiver))
            else:
                [p1Flow, p2Flow, p3Flow] = operateForFixedShutters(qPowerhouse, p1Elev, p2Elev, p3Elev, wqTarget, opElevs, shutterLevelTemps)

    # Set flows
    setPenstockFlow(network, currentRuntimestep, p1Flow, 1)
    setPenstockFlow(network, currentRuntimestep, p2Flow, 2)
    setPenstockFlow(network, currentRuntimestep, p3Flow, 3)
    if debugOutput: network.printMessage("Final penstock flows: " + str(p1Flow) + ", " + str(p2Flow) + ", " + str(p3Flow))

    # Set shutter elevations
    setShutterElev(network, currentRuntimestep, p1Elev, 1)
    setShutterElev(network, currentRuntimestep, p2Elev, 2)
    setShutterElev(network, currentRuntimestep, p3Elev, 3)
    if debugOutput: network.printMessage("Final shutter elevations: " + str(p1Elev) + ", " + str(p2Elev) + ", " + str(p3Elev))

    if qPowerhouse > lowFlowThreshold:
        outletTemp = calcOutletTemp(p1Flow, p2Flow, p3Flow, p1Elev, p2Elev, p3Elev, opElevs, shutterLevelTemps)
        if debugOutput: network.printMessage("Target temp: " + str(wqTarget))
        if debugOutput: network.printMessage("Avg penstock temp: " + str(outletTemp))

    # report back
    tcdFlows = getTCDFlowsForShutterElev(p1Flow, p1Elev)
    # Add leakage through bottom of penstock 1
    tcdFlows[0] += qLeakage
    totalP1flow = p1Flow + qLeakage

    return tcdFlows, totalP1flow
