"""Frozen ordinary single-call decision baseline; no candidate or verification input."""
DECIDE = '''Use the provided chart and public task to choose the next task option.
Briefly cite the chart and task evidence relevant to the requested comparison
and route. Keep the specified entities, time period, units and comparison scope.
Choose an exact public option. If the available evidence does not justify any
option, return null and state the concrete limitation. Do not use unavailable
data or execute a business submission. Return the requested JSON.'''
