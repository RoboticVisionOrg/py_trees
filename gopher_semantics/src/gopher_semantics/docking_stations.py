#
# License: Yujin
#
##############################################################################
# Description
##############################################################################

"""
.. module:: docking_stations
   :platform: Unix
   :synopsis: Semantics for docking stations.

Definitions, loading and publishing of docking station semantics.

----

"""

##############################################################################
# Imports
##############################################################################

import geometry_msgs.msg as geometry_msgs
import gopher_semantic_msgs.msg as gopher_semantic_msgs
import rocon_console.console as console
import rospy

##############################################################################
# Docking Stations
##############################################################################


class DockingStations(dict):
    '''
    Repository of docking station knowledge. Each docking station should be provided in yaml
    in the following form:

    .. code-block:: yaml

       docking_stations:
         '0':
           primary_id: 0
           left_id: 4
           right_id: 5
           pose:
             x : 1.0
             y : -2.0
             theta : -1.570

    Note that the key (name) is currently unused and can be anything. It should be unique to
    guarantee that the primary_id's are not overwritten.

    Parameters:

    - ~semantics_parameter_namespace : where it can find semantics information on the ros parameter server.
    '''
    def __init__(self, semantics_parameter_namespace=None, from_yaml_object=None):
        """
        Load from the rosparam server or from yaml object.
        """
        super(DockingStations, self).__init__()
        data = from_yaml_object
        if data is None:
            # look to the rosparam server
            if semantics_parameter_namespace is None:
                semantics_parameter_namespace = rospy.get_param('~semantics_parameter_namespace', rospy.resolve_name('~'))
            data = rospy.get_param(semantics_parameter_namespace + "/docking_stations", {})
        for docking_station_name, docking_station_parameters in data.iteritems():
            try:
                docking_station = gopher_semantic_msgs.DockingStation()
                docking_station.primary_id = docking_station_parameters['primary_id']
                docking_station.left_id = docking_station_parameters['left_id']
                docking_station.right_id = docking_station_parameters['right_id']
                docking_station.pose = geometry_msgs.Pose2D()
                docking_station.pose.x = docking_station_parameters['pose']['x']
                docking_station.pose.y = docking_station_parameters['pose']['y']
                docking_station.pose.theta = docking_station_parameters['pose']['theta']
                self.__setitem__(docking_station_name, docking_station)
            except KeyError:
                rospy.logwarn("Docking Stations : one of the expected fields for docking station '%s' was missing!" % docking_station_name)

    def __str__(self):
        s = console.bold + "\nDocking Stations:\n" + console.reset
        for docking_station_name in sorted(self):
            s += console.green + "  %s\n" % docking_station_name
            docking_station_msg = dict.__getitem__(self, docking_station_name)
            for key in docking_station_msg.__slots__:
                value = getattr(docking_station_msg, key)
                if isinstance(value, geometry_msgs.Pose2D):
                    s += console.cyan + "    %s: " % key + console.yellow + "{ x: %s y: %s theta: %s }\n" % (value.x, value.y, value.theta)
                else:
                    s += console.cyan + "    %s: " % key + console.yellow + "%s\n" % (value if value is not None else '-')
        s += console.reset
        return s

    def to_msg(self):
        msg = gopher_semantic_msgs.DockingStations()
        msg.docking_stations = []
        for docking_station in self.values():
            msg.docking_stations.append(docking_station)
        return msg

    def find_docking_stations_with_ar_marker_id(self, primary=None, left=None, right=None, id_list=[]):
        '''Get the dict of docking stations which have the given ids in the given
        locations. Keys are the docking station name. The id list can be used to
        provide additional ids which can match in any position. For example, if
        we pass primary=1, id_list=[2,3] we will find all stations which have 1
        as the primary id and ids 2 and 3 as the left or right marker ids.

        Note: Does not currently deal with the possibility of having multiple
        instances of the same marker id on one station

        '''
        matches = {}
        for name,station in self.iteritems():
            if primary and station.primary_id != primary:
                continue
            if left and station.left_id != left:
                continue
            if right and station.right_id != right:
                continue
            if id_list:
                station_ids = [station.primary_id, station.left_id, station.right_id]
                valid = [req_id in station_ids for req_id in id_list]
                if not all(valid):
                    continue

            matches[name] = station

        return matches

    def spin(self):
        rospy.spin()
