"""Two-phase tabular-answering baseline in the style of Tonglet et al. (2025):
transcribe the chart into a table, then decide from the table without the image.
Implemented for this revision experiment; not a rerun of their released system.
"""
TRANSCRIBE = '''From the chart image, transcribe only the data the public
task's comparison needs into the "rows" array: each row is
[series, x, y] with y exactly as printed ("unprinted" if not
printed), at most 24 rows total. Put axis orientation, ranges,
and units in "note". Nothing else.'''

DECIDE_TABLE = '''Use only the transcribed chart rows below (series/x/y triples plus
the axis note), together with the public task, to choose the next task option.
Treat the rows as your sole evidence; do not rely on any memory of an image.
First name the rows relevant to the requested comparison, then apply the
task's comparison and scope conditions to them. Choose an exact public option.
If the rows do not justify any option, return null and state the concrete
limitation. Return the requested JSON.'''
