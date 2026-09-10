"""FLDOE Master School Identification (MSID) file.

The authoritative FLDOE directory of PK-12 public schools: district number +
school number (the key the assessment workbooks use), school name, mailing and
physical addresses, LATITUDE/LONGITUDE, DATE_OPENED / DATE_CLOSED, and
charter / magnet / Title I / school-type flags.

`fetch` downloads it straight from the FLDOE EDS ColdFusion app
(https://eds.fldoe.org/EDS/MasterSchoolID/) — an empty POST to a
``Downloads/<name>.cfm`` endpoint with a browser User-Agent returns the
tab-delimited export, no session handshake.
"""
