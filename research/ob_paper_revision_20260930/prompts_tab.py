"""Two-phase tabular-answering baseline in the style of Tonglet et al. (2025):
transcribe the chart into a table, then decide from the table without the image.
Implemented for this revision experiment; not a rerun of their released system.
"""
TRANSCRIBE = '''Read the chart image for the public task and transcribe its data into a
markdown table. Include every visible series with its name, every x category or
date, and every printed numeric annotation (axis ticks, legend thresholds, data
values shown as labels) bound to the correct series and position. If the chart
shows stacked, multi-series, or grouped bars, keep one row per x position and
one column per series. Do not estimate values that are not printed: mark those
cells as "unprinted" and give the visual comparison in a separate note column.
Record axis orientation, axis ranges, and any scale breaks in a final note row.'''

DECIDE_TABLE = '''Use only the transcribed chart table below, together with the public
task, to choose the next task option. Treat the table as your sole evidence; do
not rely on any memory of an image. First name the columns relevant to the
requested comparison, then apply the task's comparison and scope conditions to
those columns. Choose an exact public option. If the table does not justify any
option, return null and state the concrete limitation. Return the requested JSON.'''
