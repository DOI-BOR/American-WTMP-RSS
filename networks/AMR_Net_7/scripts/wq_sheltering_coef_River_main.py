# no return values are used by the compute from this script.
#
# variables that are available to this script during the compute:
# 	currentVariable - the StateVariable that holds this script
# 	currentRuntimestep - the current RunTime step 
# 	network - the ResSim network

# The following represents an undefined value in a time series
# 	Constants.UNDEFINED
# throw a hec.rss.lang.StopComputeException from anywhere in the script to
# have ResSim stop the compute.
# from hec.rss.lang import StopComputeException
# raise StopComputeException("the reason to stop the compute")

# add your code here...


# to set the StateVariable's value use:
# 	currentVariable.setValue(currentRuntimestep, newValue)
# where newValue is the value you want to set it to.


from hec.model import SeasonalRecord

# These are minutes from the start of the year (in format day-of-year * 1440 min/day)
times =[1, 60 * 1440, 90 * 1440, 300 * 1440, 330 * 1440, 365 * 1440]

#vals = [0.6, 0.6, 0.0, 0.0, 0.6, 0.6]
vals = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

sr = SeasonalRecord()
sr.setArrays(times, vals)
v = sr.interpolate(currentRuntimestep.getHecTime())
currentVariable.setValue(currentRuntimestep, v)
