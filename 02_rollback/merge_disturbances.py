# ---------------------------------------------------------------------------
# 01_MergeDisturbances.py
#
#Author: Byron Smiley
#Date: 2016_12_15
#
# Description: Takes all disturbances in two directories (wildfire and harvest) and
# merges the shape files into a single dataset merging the first inputs field values
# over others were overlap exists (this can be edited.)
#
#Processing time: 48 min 22 sec on A105338 (longer)
# ---------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------------------------------------------------------------------------
## New

# Imports
import os
import archook
archook.get_arcpy()
import arcpy


class MergeDisturbances (object):
    def __init__(self, workspace, disturbances, ProgressPrinter):
        self.ProgressPrinter = ProgressPrinter
        arcpy.env.overwriteOutput = True
        self.workspace = workspace
        self.grid = r"{}\XYgrid".format(workspace)
        self.output = r"{}\MergedDisturbances_polys".format(workspace)
        self.gridded_output = r"{}\MergedDisturbances".format(workspace)

        self.distWS = disturbances
        # for disturbance in disturbances if disturbance.standReplacing==1:
        #     self.distWS.append(disturbance)

    def runMergeDisturbances(self):
        pp = self.ProgressPrinter.newProcess("merge disturbances", 3).start()
        pp.updateProgressV(0)
        self.spatialJoin()
        pp.updateProgressV(1)
        self.prepFieldMap()
        pp.updateProgressV(2)
        self.mergeLayers()
        pp.updateProgressV(3)
        pp.finish()

    def spatialJoin(self):
        target_features = arcpy.GetParameterAsText(0)
        join_features = arcpy.GetParameterAsText(1)
        out_fc = arcpy.GetParameterAsText(2)
        keep_all = arcpy.GetParameter(3)
        spatial_rel = arcpy.GetParameterAsText(4).lower()

        self.SpatialJoinLargestOverlap(target_features, join_features, out_fc, keep_all, spatial_rel)

    def prepFieldMap(self):
        fm_year = arcpy.FieldMap()
        self.fms = arcpy.FieldMappings()

        # Get the field names for all original files
        NBAC_yr = "EDATE"
        NFDB_yr = "YEAR_"
        CC_YR = "HARV_YR"

        self.vTab = arcpy.ValueTable()
        for ws in self.distWS:
            arcpy.env.workspace = ws
            fcs1 = arcpy.ListFeatureClasses("NFDB*", "Polygon")
            print "Old fire list is: "
            print fcs1
            for fc in fcs1:
                if fc!=[]:
                    fc = os.path.join(ws, fc)
                    self.fms.addTable(fc)
                    fm_year.addInputField(fc, NFDB_yr)
                    self.vTab.addRow(fc)
            fcs2 = arcpy.ListFeatureClasses("NBAC*", "Polygon")
            print "New fire list is: "
            print fcs2
            for fc in fcs2:
                if fc!=[]:
                    fc = os.path.join(ws, fc)
                    self.fms.addTable(fc)
                    fm_year.addInputField(fc, NBAC_yr, 0,3)
                    self.vTab.addRow(fc)
            harvest = arcpy.ListFeatureClasses("BC_cutblocks90_15*", "Polygon")
            print "Cutblocks list is: "
            print harvest
            for fc in harvest:
                if fc!=[]:
                    fc = os.path.join(ws, fc)
                    self.fms.addTable(fc)
                    fm_year.addInputField(fc, CC_YR)
                    self.vTab.addRow(fc)

        # Set the merge rule to find the First value of all fields in the
        # FieldMap object
        fm_year.mergeRule = 'First'
        print "vTab equals: "
        print self.vTab
        # Set the output field properties for FieldMap objects
        field_name = fm_year.outputField
        field_name.name = 'DistYEAR'
        field_name.aliasName = 'DistYEAR'
        fm_year.outputField = field_name

        # Add the FieldMap objects to the FieldMappings object
        self.fms.addFieldMap(fm_year)

    def mergeLayers(self):
        arcpy.env.workspace = self.workspace
        arcpy.Merge_management(self.vTab, self.output, self.fms)
        self.SpatialJoinLargestOverlap(self.grid, self.output, self.gridded_output, False, "largest_overlap")

# Spatial Join tool--------------------------------------------------------------------
# Main function, all functions run in SpatialJoinOverlapsCrossings
    def SpatialJoinLargestOverlap(self, target_features, join_features, out_fc, keep_all, spatial_rel):
        if spatial_rel == "largest_overlap":
            # Calculate intersection between Target Feature and Join Features
            intersect = arcpy.analysis.Intersect([target_features, join_features], "in_memory/intersect", "ONLY_FID")
            # Find which Join Feature has the largest overlap with each Target Feature
            # Need to know the Target Features shape type, to know to read the SHAPE_AREA oR SHAPE_LENGTH property
            geom = "AREA" if arcpy.Describe(target_features).shapeType.lower() == "polygon" and arcpy.Describe(join_features).shapeType.lower() == "polygon" else "LENGTH"
            fields = ["FID_{0}".format(os.path.splitext(os.path.basename(target_features))[0]),
                      "FID_{0}".format(os.path.splitext(os.path.basename(join_features))[0]),
                      "SHAPE@{0}".format(geom)]
            overlap_dict = {}
            with arcpy.da.SearchCursor(intersect, fields) as scur:
                for row in scur:
                    try:
                        if row[2] > overlap_dict[row[0]][1]:
                            overlap_dict[row[0]] = [row[1], row[2]]
                    except:
                        overlap_dict[row[0]] = [row[1], row[2]]

            # Copy the target features and write the largest overlap join feature ID to each record
            # Set up all fields from the target features + ORIG_FID
            fieldmappings = arcpy.FieldMappings()
            fieldmappings.addTable(target_features)
            fieldmap = arcpy.FieldMap()
            fieldmap.addInputField(target_features, arcpy.Describe(target_features).OIDFieldName)
            fld = fieldmap.outputField
            fld.type, fld.name, fld.aliasName = "LONG", "ORIG_FID", "ORIG_FID"
            fieldmap.outputField = fld
            fieldmappings.addFieldMap(fieldmap)
            # Perform the copy
            arcpy.conversion.FeatureClassToFeatureClass(target_features, os.path.dirname(out_fc), os.path.basename(out_fc), "", fieldmappings)
            # Add a new field JOIN_FID to contain the fid of the join feature with the largest overlap
            arcpy.management.AddField(out_fc, "JOIN_FID", "LONG")
            # Calculate the JOIN_FID field
            with arcpy.da.UpdateCursor(out_fc, ["ORIG_FID", "JOIN_FID"]) as ucur:
                for row in ucur:
                    try:
                        row[1] = overlap_dict[row[0]][0]
                        ucur.updateRow(row)
                    except:
                        if not keep_all:
                            ucur.deleteRow()
            # Join all attributes from the join features to the output
            joinfields = [x.name for x in arcpy.ListFields(join_features) if not x.required]
            arcpy.management.JoinField(out_fc, "JOIN_FID", join_features, arcpy.Describe(join_features).OIDFieldName, joinfields)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------
## Old Script
'''
env.overwriteOutput = True
print "Start time: " +(time.strftime('%a %H:%M:%S'))

# Spatial Join tool--------------------------------------------------------------------
# Main function, all functions run in SpatialJoinOverlapsCrossings
def SpatialJoinLargestOverlap(target_features, join_features, out_fc, keep_all, spatial_rel):
    if spatial_rel == "largest_overlap":
        # Calculate intersection between Target Feature and Join Features
        intersect = arcpy.analysis.Intersect([target_features, join_features], "in_memory/intersect", "ONLY_FID")
        # Find which Join Feature has the largest overlap with each Target Feature
        # Need to know the Target Features shape type, to know to read the SHAPE_AREA oR SHAPE_LENGTH property
        geom = "AREA" if arcpy.Describe(target_features).shapeType.lower() == "polygon" and arcpy.Describe(join_features).shapeType.lower() == "polygon" else "LENGTH"
        fields = ["FID_{0}".format(os.path.splitext(os.path.basename(target_features))[0]),
                  "FID_{0}".format(os.path.splitext(os.path.basename(join_features))[0]),
                  "SHAPE@{0}".format(geom)]
        overlap_dict = {}
        with arcpy.da.SearchCursor(intersect, fields) as scur:
            for row in scur:
                try:
                    if row[2] > overlap_dict[row[0]][1]:
                        overlap_dict[row[0]] = [row[1], row[2]]
                except:
                    overlap_dict[row[0]] = [row[1], row[2]]

        # Copy the target features and write the largest overlap join feature ID to each record
        # Set up all fields from the target features + ORIG_FID
        fieldmappings = arcpy.FieldMappings()
        fieldmappings.addTable(target_features)
        fieldmap = arcpy.FieldMap()
        fieldmap.addInputField(target_features, arcpy.Describe(target_features).OIDFieldName)
        fld = fieldmap.outputField
        fld.type, fld.name, fld.aliasName = "LONG", "ORIG_FID", "ORIG_FID"
        fieldmap.outputField = fld
        fieldmappings.addFieldMap(fieldmap)
        # Perform the copy
        arcpy.conversion.FeatureClassToFeatureClass(target_features, os.path.dirname(out_fc), os.path.basename(out_fc), "", fieldmappings)
        # Add a new field JOIN_FID to contain the fid of the join feature with the largest overlap
        arcpy.management.AddField(out_fc, "JOIN_FID", "LONG")
        # Calculate the JOIN_FID field
        with arcpy.da.UpdateCursor(out_fc, ["ORIG_FID", "JOIN_FID"]) as ucur:
            for row in ucur:
                try:
                    row[1] = overlap_dict[row[0]][0]
                    ucur.updateRow(row)
                except:
                    if not keep_all:
                        ucur.deleteRow()
        # Join all attributes from the join features to the output
        joinfields = [x.name for x in arcpy.ListFields(join_features) if not x.required]
        arcpy.management.JoinField(out_fc, "JOIN_FID", join_features, arcpy.Describe(join_features).OIDFieldName, joinfields)


# Run the script
if __name__ == '__main__':
    # Get Parameters
    target_features = arcpy.GetParameterAsText(0)
    join_features = arcpy.GetParameterAsText(1)
    out_fc = arcpy.GetParameterAsText(2)
    keep_all = arcpy.GetParameter(3)
    spatial_rel = arcpy.GetParameterAsText(4).lower()

    SpatialJoinLargestOverlap(target_features, join_features, out_fc, keep_all, spatial_rel)
    print "finished"
# End of Spatial Join tool--------------------------------------------------------------------
# VARIABLES:
workspace = r"H:\Nick\GCBM\00_Testing\05_working\02_layers\01_external_spatial_data\00_Workspace.gdb"
# Disturbance Input workspaces
distWS = [r"H:\Nick\GCBM\00_Testing\05_working\02_layers\01_external_spatial_data\03_disturbances\01_historic\02_harvest",  r"H:\Nick\GCBM\00_Testing\05_working\02_layers\01_external_spatial_data\03_disturbances\01_historic\01_fire\shapefiles"]

grid = r"{}\XYgrid_1ha".format(workspace)
output = r"{}\MergedDisturbances_polys".format(workspace)
gridded_output = r"{}\MergedDisturbances".format(workspace)
# PROCESSES
# Create field map
# Create the required FieldMap and FieldMappings objects
print "Prepping Field Map...."
fm_year = arcpy.FieldMap()
fms = arcpy.FieldMappings()

# Get the field names for all original files
NBAC_yr = "EDATE"
NFDB_yr = "YEAR_"
CC_YR = "HARV_YR"

fc_list = []
vTab = arcpy.ValueTable()
for ws in distWS:
    arcpy.env.workspace = ws
    fcs1 = arcpy.ListFeatureClasses("NFDB*", "Polygon")
    print "Old fire list is: "
    print fcs1
    for fc in fcs1:
        if fc!=[]:
            fc = os.path.join(ws, fc)
            fms.addTable(fc)
            fm_year.addInputField(fc, NFDB_yr)
            vTab.addRow(fc)
    fcs2 = arcpy.ListFeatureClasses("NBAC*", "Polygon")
    print "New fire list is: "
    print fcs2
    for fc in fcs2:
        if fc!=[]:
            fc = os.path.join(ws, fc)
            fms.addTable(fc)
            fm_year.addInputField(fc, NBAC_yr, 0,3)
            vTab.addRow(fc)
    harvest = arcpy.ListFeatureClasses("BC_cutblocks90_15*", "Polygon")
    print "Cutblocks list is: "
    print harvest
    for fc in harvest:
        if fc!=[]:
            fc = os.path.join(ws, fc)
            fms.addTable(fc)
            fm_year.addInputField(fc, CC_YR)
            vTab.addRow(fc)

# Set the merge rule to find the First value of all fields in the
# FieldMap object
fm_year.mergeRule = 'First'
print "vTab equals: "
print vTab
# Set the output field properties for FieldMap objects
field_name = fm_year.outputField
field_name.name = 'DistYEAR'
field_name.aliasName = 'DistYEAR'
fm_year.outputField = field_name

# Add the FieldMap objects to the FieldMappings object
fms.addFieldMap(fm_year)
#Merge Layers
print "Merging layers..."
arcpy.env.workspace = workspace
arcpy.Merge_management(vTab, output, fms)
SpatialJoinLargestOverlap(grid, output, gridded_output, False, "largest_overlap")

print "End time: " +(time.strftime('%a %H:%M:%S'))
print "COMPLETE"
'''
