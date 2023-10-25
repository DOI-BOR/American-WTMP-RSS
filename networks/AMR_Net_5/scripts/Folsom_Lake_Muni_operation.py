# required imports to create the OpValue return object.
from hec.model import RunTimeStep
from hec.rss.model import OpController
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.rss.model import ReservoirElement
from hec.rss.plugins.waterquality.model import RssWQGeometry
from hec.rss.wq.model import WQRun
from hec.script import Constants
from hec.wqenginecore import WQEngineAdapter
from hec.wqenginecore import WQResHydro
from hec.wqenginecore.geometry import SubDomain
from hec.wqenginecore.geometry import WQControlDevice
from java.util import Vector

# 
# initialization function. optional.
#
# set up tables and other things that only need to be performed once during
# the compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
#
#
def initRuleScript(currentRule, network):
	# return Constants.TRUE if the initialization is successful
	# and Constants.FALSE if it failed.  Returning Constants.FALSE
	# will halt the compute.
	return Constants.TRUE


# runRuleScript() is the entry point that is called during the
# compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
# currentRuntimestep is the current Run Time Step
def runRuleScript(currentRule, network, currentRuntimestep):

	globalVarName = "Muni_flow_calib"
	
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	flowVal = globVar.getCurrentValue(currentRuntimestep)
	
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

	setTCDoperation(currentRule, flowVal, resElev)

	# create new Operation Value (OpValue) to return
	opValue = OpValue()

	opValue.init(OpRule.RULETYPE_SPEC, flowVal)

	return opValue


#######################################################################################################
# Check whether a value is valid
def isValidValue(value):
	if not value:
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
def setTCDoperation(currentRule, flowVal, resElev):

	# Fill TCD inlet flow array - only 1 inlet
	tcdFlows = []
	tcdFlows.append(flowVal)
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)
		
	# Change withdrawal elevation, depending on state of res stratification
	wqRun = network.getRssRun().getWQRun()
	engineAdapter = wqRun.getWqEngineAdapter()
	resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
	resLayerElevs = resWQGeoSubdom.getResVerticalLayerBoundaries()
	numLayers = len(resLayerElevs)-1
	layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)

	# Find correct elevation - use highest possible
	targetTemp = 18.
	maxElev = 401.
	minElev = 317.
	targetLayer = 0
	for k in reversed(range(numLayers)):
		layerBotElev = resLayerElevs[k]
		layerTemp = layerTemps[k]
		if ((layerBotElev < maxElev and layerBotElev < resElev and layerTemp < targetTemp)
			or layerBotElev < minElev):
			targetLayer = k
			break
	targetElev = resLayerElevs[targetLayer]

	# Reallocate WQCD geometry in WQ Engine
	elevs = [targetElev]
	isRect = [True]
	heights = [1.]
	widths = [1.]
	diameters = [1.]
	releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
	irtn = engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, len(elevs), elevs, isRect, heights, widths, diameters)
	if irtn != 0:
		return Constants.FALSE
	else:
		return Constants.TRUE

	return
