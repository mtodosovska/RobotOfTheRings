#!/usr/bin/env python
import roslib
roslib.load_manifest('localizer')
import rospy
import sys, select, termios, tty
from std_msgs.msg import String, Bool, ColorRGBA
import sensor_msgs.msg
import message_filters
import collections
from detection_msgs.msg import Detection
from localizer.srv import Localize
from sensor_msgs.msg import CameraInfo
from visualization_msgs.msg import Marker, MarkerArray
from image_geometry import PinholeCameraModel
from geometry_msgs.msg import Point, Vector3
import math
from tf import TransformListener
import geometry_msgs.msg
import rospy
from std_msgs.msg import String

numFaces = 1
counter = 0
maxDistance = 0.9
alreadyDetected = [] # an array containing n points, the first n detected that were considered the same detection
n = 3 # number of points required in order to determine that the detection is a face
detected = [] #an array with the already passed faces
class DetectionMapper():

    def camera_callback(self, camera_info):
        self.camera_infos.append(camera_info)
        
    def distance(self, d1, d2):
		p1 = d1.pose.position
		p2 = d2.pose.position
		xd = p1.x - p2.x
		yd = p1.y - p2.y
		dd = xd ** 2 + yd ** 2
		res = math.sqrt(dd)
		return res 


    def detections_callback(self, detection):
		print("Entered in the callback function")
		global counter
		global maxDistance #the maximal distance between two points required for them to be considered the same detection	
		global alreadyDetected 
		global n 
		global lastAdded	
		global detected
		#global tf
		global numFaces

		u = detection.pose.position.x
		v = detection.pose.position.y
		#detection.header.stamp = rospy.Time.now() #call rospy.init_node() before this to work

		camera_info = None
		best_time = 100
		for ci in self.camera_infos:
			time = abs(ci.header.stamp.to_sec() - detection.header.stamp.to_sec())
			if time < best_time:
				camera_info = ci
				best_time = time

		if not camera_info or best_time > 1:
			print("Best time is higher than 1")
			return

		camera_model = PinholeCameraModel()
		camera_model.fromCameraInfo(camera_info)

		point = Point(((u - camera_model.cx()) - camera_model.Tx()) / camera_model.fx(),
             ((v - camera_model.cy()) - camera_model.Ty()) / camera_model.fy(), 1)

		localization = self.localize(detection.header, point, self.region_scope)
		transformedPoint = point
		if not localization:
			return


		now = detection.header.stamp
		self.tf.waitForTransform("camera_rgb_optical_frame", "map", now, rospy.Duration(5.0))

		m = geometry_msgs.msg.PoseStamped()
		m.header.frame_id = "camera_rgb_optical_frame"
		m.pose = localization.pose
		m.header.stamp = detection.header.stamp
		transformedPoint = self.tf.transformPose("map", m)
		
		#print(m.pose.position.x)
		#print(m.pose.position.y)

		self.pub.publish(transformedPoint)	
		
		if( localization.pose.position.x != 0.0):

			#print("Localisation: ", localization)
			#print("Transformation: ", transformedPoint)
			#print("Point: ", point)
			
			if counter == 0:
				#print("Counter is zero.")
				counter+=1
				lastAdded = transformedPoint
				#print("Adding the point to the array.")
				#alreadyDetected.append(transformedPoint)
				#print(len(alreadyDetected))
			else:
				#print("Counter: ", counter)
				dist = self.distance(transformedPoint, lastAdded)
				
				#print("Number of detected faces so far: ", len(detected))
				print("Distance is ", dist)
				
				if dist <= maxDistance:
					#print("-----------Less then max----------------------------------")
					if counter < 2 or counter >= 2 :
						#alreadyDetected.append(transformedPoint)
						#print(len(alreadyDetected))			
						lastAdded = transformedPoint
						counter += 1
						beenDetected = False
						for p in detected:
							#print("Checking already detected")
							#print("Distance: ", self.distance(p, transformedPoint))
							
							if self.distance(p, transformedPoint) <= maxDistance:
								#print("This face has already been detected")
								#print("Distance: ", self.distance(p, transformedPoint))
								beenDetected = True
								break
							
						if(beenDetected == False):
							print("-----------------Good to go------------------------")
							detected.append(lastAdded)
				
							marker = Marker()
							#print("Localisation: ", localization)
							marker.header.stamp = detection.header.stamp
							marker.header.frame_id = detection.header.frame_id
							marker.pose = localization.pose
							marker.type = Marker.CUBE
							marker.action = Marker.ADD
							marker.frame_locked = False
							marker.lifetime = rospy.Duration.from_sec(1)
							marker.id = self.marker_id_counter
							marker.scale = Vector3(0.1, 0.1, 0.1)
							marker.color = ColorRGBA(1, 0, 0, 1)
							self.markers.markers.append(marker)
							self.marker_id_counter += 1
							self.soundhandle.say("I detected a face.", blocking = False)
							print("Number of detected faces: ", len(detected))							
							if len(detected) == numFaces:
								#publish stop
								
								#rospy.init_node('mapper', anonymous=True)								
								#msg = String()
								#msg.data = "Found all faces."
								print("Sending shutdown")
								

							
				else:
					#print("-----------------------------------------More then max----")
					lastAdded = transformedPoint
					
		else:
			print("Localisation: ", localization)


    def flush(self):
        if not self.markers.markers:
            self.markers = MarkerArray()
            return
        self.markers_pub.publish(self.markers)
        #self.markers = MarkerArray()

    def __init__(self):
		numFaces = 1
		counter = 0
		maxDistance = 0.9
		alreadyDetected = [] # an array containing n points, the first n detected that were considered the same detection
		n = 3 # number of points required in order to determine that the detection is a face
		detected = []
		self.tf = TransformListener()
		self.markers = MarkerArray()
		self.marker_id_counter = 0 
		self.region_scope = rospy.get_param('~region', 3)
		self.buffer_size = rospy.get_param('~camera_buffer_size', 50)
		rospy.wait_for_service('localizer/localize')
		self.pub = rospy.Publisher('ring_position', geometry_msgs.msg.PoseStamped)
		self.camera_infos = collections.deque(maxlen = self.buffer_size)
		self.detections_sub = message_filters.Subscriber('blob_topic', geometry_msgs.msg.PoseStamped)
		self.detections_sub.registerCallback(self.detections_callback)

		self.camera_sub = message_filters.Subscriber('/camera/depth_registered/camera_info', CameraInfo)
		self.camera_sub.registerCallback(self.camera_callback)


		self.localize = rospy.ServiceProxy('localizer/localize', Localize)
		self.markers_pub = rospy.Publisher('markers', MarkerArray)
   
if __name__ == '__main__':

	rospy.init_node('mapper')
	print("Above try")
	try:
		print("Under try")
		mapper = DetectionMapper()
		print("Mapper created")
		r = rospy.Rate(30)
		while not rospy.is_shutdown():
			mapper.flush()
			r.sleep()
	except rospy.ROSInterruptException: pass
