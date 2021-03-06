import inspect
import os
import logging
import random
import numpy as np
from preprocess_tools.licensemanager import *

class GenerateSlashburn(object):
    def __init__(self, ProgressPrinter):
        logging.info("Initializing class {}".format(self.__class__.__name__))
        self.ProgressPrinter = ProgressPrinter

    def generateSlashburn(self, inventory, harvest_poly_shp, year_field, year_range, sb_percent):
        pp = self.ProgressPrinter.newProcess(inspect.stack()[0][3], len(year_range), 1).start()
        PercSBofCC = sb_percent

        logging.info('Prepping temporary workspace')
        temp_gdb = os.path.join(os.path.dirname(harvest_poly_shp),"slashburn_temp.gdb")
        with arc_license(Products.ARC) as arcpy:
            if os.path.exists(temp_gdb):
                arcpy.Delete_management(temp_gdb)
            arcpy.CreateFileGDB_management(os.path.dirname(harvest_poly_shp), "slashburn_temp.gdb")
            arcpy.env.workspace = os.path.join(os.path.dirname(harvest_poly_shp),"slashburn_temp.gdb")
            arcpy.env.overwriteOutput = True

            logging.info('Copying MergedDisturbances from inventory workspace')
            arcpy.FeatureClassToFeatureClass_conversion(os.path.join(inventory.getWorkspace(),"MergedDisturbances"),
                arcpy.env.workspace, "MergedDisturbances")
            arcpy.MakeFeatureLayer_management("MergedDisturbances", "temp_harvest")
            if "DistType" not in [f.name for f in arcpy.ListFields("temp_harvest")]:
                arcpy.AddField_management("temp_harvest", "DistType", "SHORT")
            arcpy.CreateFeatureclass_management(arcpy.env.workspace, "slashburn", "POLYGON", "temp_harvest", "SAME_AS_TEMPLATE", "SAME_AS_TEMPLATE", "temp_harvest")
            logging.info('Making slashburn for the range {}-{}'.format(year_range[0],year_range[-1]))
            logging.info('Selecting {}% of the harvest area in each year as slashburn...'.format(PercSBofCC))
            # Create SB records for each timestep
            for year in year_range:
                # Select only records corresponding to the current year being processed
                expression2 = '{} = {}'.format(arcpy.AddFieldDelimiters("temp_harvest", year_field), year)
                arcpy.SelectLayerByAttribute_management("temp_harvest", "NEW_SELECTION", expression2)
                # Select only records that intersect with the inventory and are harvest disturbances
                # Note assumption: Harvest disturbance if the harvest year field value = disturbance year field value
                # This assumption is used in the rollback update_inventory as well
                filter = "CELL_ID > 0 AND {} = {}".format(year_field, inventory.getFieldNames()['disturbance_yr'])
                arcpy.SelectLayerByAttribute_management("temp_harvest", "SUBSET_SELECTION", filter)
                if int(arcpy.GetCount_management("temp_harvest").getOutput(0)) > 0:
                    number_features = [row[0] for row in arcpy.da.SearchCursor("temp_harvest", "OBJECTID")]
                    temp_harvest_count = int(arcpy.GetCount_management("temp_harvest").getOutput(0))
                    features2Bselected = random.sample(number_features,(int(np.ceil(round(float(temp_harvest_count * PercSBofCC)/100)))))
                    features2Bselected.append(0)
                    features2Bselected = str(tuple(features2Bselected)).rstrip(',)') + ')'
                    selectExpression = '{} IN {}'.format(arcpy.AddFieldDelimiters("temp_harvest", "OBJECTID"), features2Bselected)
                    arcpy.SelectLayerByAttribute_management("temp_harvest","NEW_SELECTION", selectExpression)
                    arcpy.CopyFeatures_management("temp_harvest","temp_SB")
                    arcpy.CalculateField_management("temp_SB", "DistType", 13, "PYTHON", "")
                    arcpy.Append_management("temp_SB", "slashburn")
                arcpy.SelectLayerByAttribute_management("temp_harvest", "CLEAR_SELECTION")
                pp.updateProgressP()

            sb_shp = os.path.join(os.path.dirname(harvest_poly_shp), "slashburn.shp")
            if arcpy.Exists(sb_shp):
                arcpy.Delete_management(sb_shp)
            logging.info('Saving slashburn to {}'.format(sb_shp))
            arcpy.CopyFeatures_management("slashburn", sb_shp)

            logging.info('Deleting temporary workspace')
            arcpy.Delete_management("slashburn")
            arcpy.Delete_management("temp_harvest")
            arcpy.Delete_management("temp_SB")
            arcpy.Delete_management(temp_gdb)

            pp.finish()
            return sb_shp
