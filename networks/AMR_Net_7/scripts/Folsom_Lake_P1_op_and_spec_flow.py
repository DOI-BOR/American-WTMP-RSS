from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

# Script "Global variables"
# Shutter operations
startOpDate = date(3000, 5, 1)  # May 1st
endOpDate = date(3000, 11, 1)  # Nov 1st
temperatureThreshold = 0.5
maxViolationDays = 4
checkOpHour = 19  # Hour to do operations check
gateOpLookbackDays = 2  # For operations outside of target op period
# Variable names
globalVarNameShutterElevForecast = 'PX_shutter_elev_forecast'
globalVarNameShutterElevHist = 'PX_shutter_elev'
globalVarNamePSFlow = 'PX_flow_forecast'
globalVarNameRRFlow = 'Lower_RO_flow_forecast'
globalVarNameTempTarget = 'Temp_Target'
stateVarNameViolations = 'Temp_Target_Violations'
stateVarNameShutterLevel = 'Shutter_Level'
# Script constants
temperatureConstitId = 1
lastIterationPassNum = 2


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
def initRuleScript(currentRule, network):

	applyRule = checkApplyRule(currentRule, network)

	# Handle case where rule is active but disabled or WQ for reservoir is not being run
	if not applyRule:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation. Rule will be ignored.")
		return Constants.TRUE

	# WQ is being simulated
	else:
		# Reallocate WQCD geometry in WQ Engine to move withdrawal centerline higher
		offset = 8.9
		elevs = [307., 323., 336., 349., 362., 401.]
		nLevels = len(elevs)
		isRect = []
		heights = []
		widths = []
		diameters = []
		for k in range(nLevels):
			if k > 0:  # don't adjust lowest level because of penstock intakes
				elevs[k] += offset
			isRect.append(True)
			heights.append(0.)
			widths.append(0.)
			diameters.append(0.)
		resOp = currentRule.getController().getReservoirOp()
		releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
		engineAdapter = wqRun.getWqEngineAdapter()
		resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
		engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, nLevels, elevs, isRect, heights, widths, diameters)
		# Initialization for first time step
		setTempTargetViolations(network, -99)
	
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

	# Only evaluate WQ part of script running WQ and computer iteration > 0
	#  (On 0th iteration, only local res decisions being evaluated and WQ is not being run yet)
	computeIter = currentRule.getComputeIteration()
	evalRule = currentRule.getEvalRule() and (computeIter >= lastIterationPassNum)
	
	if evalRule:
		# Get flow and temperature information
		# Flows broken down into powerhouse and non powerhouse
		# Temperature estimate for the non powerhouse releases
		qPowerhouse, qNonPH, tempNonPH = getReleaseInfo(currentRule, network, currentRuntimestep, True)

		# Get temperature target
		wqTarget = getTargetWQ(network, currentRuntimestep)

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
		
		tcdFlows, qPenstock1 = setForecastTCDoperation(currentRule, network, currentRuntimestep, 
								qNonPH, tempNonPH, qPowerhouse, wqTarget, resElev)
		resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, qPenstock1)

		opValue = OpValue()
		opValue.init(OpRule.RULETYPE_SPEC, qPenstock1)
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
# Get a single river outlet flow for a given time step
def getReleaseInfo(currentRule, network, currentRuntimestep, usePrevStepAsEstimate):

	# Non-powerhouse outlet names and elevations
	outletDict = {'Service Spillway': 418.,
	              'Auxiliary Spillway': 367.02,
	              'Emergency Spillway': 418., 
	              'Upper River Gates': 280.,
	              'Lower River Gates': 210.}
	powerhouseOutletName = 'Powerhouse'

	resOp = currentRule.getController().getReservoirOp()
	res = resOp.getReservoirElement()

	wqRun = network.getRssRun().getWQRun()
	engineAdapter = wqRun.getWqEngineAdapter()
	resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
	sdId = resWQGeoSubdom.getId()

	# Non-powerhouse flows and temperatures
	qNonPH = 0.
	tempNonPH = 0.
	
	for outletName, outletElev in outletDict.items():
		outletElem = res.getElementByName(outletName)
		roCntrlr = resOp.getControllerForElement(outletElem)
		flow = roCntrlr.getCurMinOpValue(currentRuntimestep).value
		if not isValidValue(flow) and usePrevStepAsEstimate:
			rts = RunTimeStep()
			rts.setStep(currentRuntimestep.getStep() - 1)
			flow = roCntrlr.getDecisionValue(rts)
		if not isValidValue(flow):
			raise ValueError("Invalid value: " + str(flow) + " for " + outletName + " flow for time step: " + str(currentRuntimestep.step))

		qNonPH += flow
		temp = engineAdapter.getConstitResultForFlowElev(sdId, temperatureConstitId, flow, outletElev)
		if temp > 100. or temp < 0.:
			message = "Temperature outside of range (0,100) for flow " + str(flow) + " elevation " + str(outletElev) + " temperature " + str(temp)
			print(message)
			raise ValueError(message)
		tempNonPH += flow * temp

	if qNonPH > 0.1:
		tempNonPH = tempNonPH / qNonPH

	# Powerhouse flow
	outletElem = res.getElementByName(powerhouseOutletName)
	roCntrlr = resOp.getControllerForElement(outletElem)
	flow = roCntrlr.getCurMinOpValue(currentRuntimestep).value
	if not isValidValue(flow) and usePrevStepAsEstimate:
		rts = RunTimeStep()
		rts.setStep(currentRuntimestep.getStep() - 1)
		flow = roCntrlr.getDecisionValue(rts)
	if not isValidValue(flow):
		raise ValueError("Invalid value: " + str(flow) + " for " + outletName + " flow for time step: " + str(currentRuntimestep.step))
	qPowerhouse = flow

	return qPowerhouse, qNonPH, tempNonPH


#######################################################################################################
# Get the water quality target value by looking for the global variable timeseries
def getTargetWQ(network, currentRuntimestep):

	convert2C = False
	
	globVar = network.getGlobalVariable(globalVarNameTempTarget)
	if not globVar:
		raise NameError("Global variable: " + globalVarNameTempTarget + " not found.")
	target = globVar.getCurrentValue(currentRuntimestep)
	
	if not isValidValue(target):
		raise ValueError("Global variable: " + globalVarNameTempTarget + " has invalid value " +
		                 str(target) + " for time step: " + str(currentRuntimestep.step))
	else:
		if convert2C:
			targetDegC = (target - 32.) * 5./9.
		else:
			targetDegC = target
		#print("Target temperature: {0:.2f}".format(targetDegC))
		return targetDegC


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
# Translate the Folsom dss gate elevation to a lowest-gate leakage fraction
def getCardnoLeakageFractionFromGateElev(elevVal):
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
# Set the forecasted penstock flow
def setPenstockFlow(rts, flow, psNum):
	gvName = globalVarNamePSFlow.replace('X', str(psNum))
	gv = network.getGlobalVariable(gvName)
	if not gv:
		raise NameError("Global variable: " + gvName + " not found.")
	gv.setValue(rts, flow)


#######################################################################################################
# Set the forecasted gate elevation
def setShutterElev(rts, elev, psNum):
	gvName = globalVarNameShutterElevForecast.replace('X', str(psNum))
	gv = network.getGlobalVariable(gvName)
	if not gv:
		raise NameError("Global variable: " + gvName + " not found.")
	gv.setValue(rts, elev)


#######################################################################################################
# Get the historical gate elevation
def getShutterElevHist(rts, psNum):
	gvName = globalVarNameShutterElevHist.replace('X', str(psNum))
	gv = network.getGlobalVariable(gvName)
	if not gv:
		raise NameError("Global variable: " + gvName + " not found.")
	return gv.getValue(rts)


#######################################################################################################
# Get the previous shutter elevation
def getPrevShutterElev(rts, psNum):
	gvName = globalVarNameShutterElevForecast.replace('X', str(psNum))
	gv = network.getGlobalVariable(gvName)
	if not gv:
		raise NameError("Global variable: " + gvName + " not found.")
	rts1 = RunTimeStep()
	rts1.setStep(max(rts.getStep()-1, 0))
	return gv.getValue(rts1)


#######################################################################################################
# Set the TCD operation for a forecast
def setForecastTCDoperation(currentRule, network, currentRuntimestep, qNonPH, tempNonPH,
		                    qPowerhouse, wqTarget, resElev):

	# Fill TCD inlet flow array
	tcdFlows = []
	nInletLevels = 6
	# Initialize flows
	for j in range(nInletLevels):
		tcdFlows.append(0.0)

	# Get previous gate elevations
	if numViolations < 0:
		# First time step
		p1ShutterElev = getShutterElevHist(currentRuntimestep, 1)
		p2ShutterElev = getShutterElevHist(currentRuntimestep, 2)
		p3ShutterElev = getShutterElevHist(currentRuntimestep, 3)
		setTempTargetViolations(network, 0)
	else:
		p1ShutterElev = getPrevShutterElev(1)
		p2ShutterElev = getPrevShutterElev(2)
		p3ShutterElev = getPrevShutterElev(3)

	# Check for elevation violations
	elevOffset = 
	if p1ShutterElev < resElev + 
	
	# Leakage
	lowerMinLeakageFlow = 44. # min cfs
	leakageFraction = getCardnoLeakageFractionFromGateElev(resElev)

	if qPowerhouse < lowerMinLeakageFlow:  # cfs
		avgFlow = qPowerhouse / 3.
		tcdFlows[0] = avgFlow
		setPenstockFlow(currentRuntimestep, avgFlow, 1)
		setPenstockFlow(currentRuntimestep, avgFlow, 2)
		setPenstockFlow(currentRuntimestep, avgFlow, 3)
		setShutterElev(currentRuntimestep, p1ShutterElev, 1)
		setShutterElev(currentRuntimestep, p2ShutterElev, 2)
		setShutterElev(currentRuntimestep, p3ShutterElev, 3)
		return tcdFlows, avgFlow
	else:
		tcdFlows[0] = lowerMinLeakageFlow + leakageFraction*(flowVal-lowerMinLeakageFlow)
		remainingFlow = (1.0-leakageFraction)*(flowVal-lowerMinLeakageFlow)

	numViolations = getTempTargetViolations(network)
	

		if p1ShutterElev == p2ShutterElev and p2ShutterElev == p3ShutterElev:
			
		


	
	curTime = currentRuntimestep.getHecTime()
	try:
		curDate = date(3000, curTime.month(), curTime.day())
	except ValueError: # Leap year issue
		curDate = date(3000, curTime.month(), curTime.day()-1)
	curHour = curTime.hour()
	iCurStep = currentRuntimestep.getStep()
	insideOpPeriod = curDate >= startOpDate and curDate <= endOpDate





		

	

	# report back 
	leakage_cfs = tcdFlows[0]
		
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
