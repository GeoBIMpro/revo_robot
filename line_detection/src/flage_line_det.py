#!/usr/bin/env python
import sys
import numpy as np
import cv2
import math
#import time
import rospy
import sensor_msgs
from sensor_msgs.msg import CompressedImage
from sensor_msgs.msg import Image
import rospkg
from dynamic_reconfigure.server import Server
from line_detection.cfg import LineDetectionConfig
from cv_bridge import CvBridge, CvBridgeError

###############################################################################
## Chicago Engineering Design Team
## Line Detection Example using Python OpenCV for autonomous robot Scipio
##    (IGVC competition).
## @author Basheer Subei
## @email basheersubei@gmail.com
#######################################################
##
## Hough Transform node
##
###############################################################################


class line_detection:

    node_name = "flag_lanedetection"
    namespace = rospy.get_namespace()
    if namespace == "/":
        namespace = ""

    use_mono = rospy.get_param(rospy.get_namespace() + node_name + "/use_mono")
    use_compressed_format = rospy.get_param(rospy.get_namespace() + node_name + "/use_compressed_format")
    subscriber_image_topic = rospy.get_param(rospy.get_namespace() + node_name + "/subscriber_image_topic")
    publisher_image_topic = rospy.get_param(rospy.get_namespace() + node_name + "/publisher_image_topic")
    buffer_size = rospy.get_param(rospy.get_namespace() + node_name + "/buffer_size")
    # this is where we define our variables in the class.
    # these are changed dynamically using dynamic_reconfig and affect
    # the image processing algorithm. A lot of these are not used in the
    # current algorithm.
    blur_size = 49

    # hsv threshold variables
    hue_low = 20
    hue_high = 50

    saturation_low = 0
    saturation_high = 255

    value_low = 0
    value_high = 255

    backprojection_threshold = 50

    # gabor filter parameters
    gabor_ksize = 4
    gabor_sigma = 7
    gabor_theta = 0
    gabor_lambd = 27
    gabor_gamma = 4

    hough_rho = 1
    hough_theta = 0.01745329251
    hough_threshold = 50
    hough_min_line_length = 50
    hough_max_line_gap = 10
    hough_thickness = 1

    # training_file_name = 'training_for_backprojection_1.png'
    training_file_name = rospy.get_param(rospy.get_namespace() + node_name + "/training_file_name")

    package_path = ''

    image_height = 0
    image_width = 0

    roi_top_left_x = 0
    roi_top_left_y = 0
    roi_width = 2000
    roi_height = 2000

    dilate_size = 0
    dilate_iterations = 0

    squares   = []
    #cnt_blue = []
    #cnt_red  = []
    xx_pos    = 0
    #i        = 0
    #cnt_max  = []
    ##########################


    def color_track(img,l_b,u_b): # ********************************************************************************************************************************* # 
        ######################
    #    img = cv2.flip(img, 1)
        ######################
        hsv = cv2.GaussianBlur(img, (5,5), 0)
        hsv = cv2.cvtColor(hsv, cv2.COLOR_BGR2HSV) 
        ######################
        lower_bounder = np.array(l_b, np.uint8)         
        upper_bounder = np.array(u_b, np.uint8)
        ######################
        mask     = cv2.inRange(hsv, lower_bounder, upper_bounder)    
        dilation = np.ones((1, 1), "uint8")
        mask     = cv2.dilate(mask, dilation)
        res      = cv2.bitwise_and(img,img, mask= mask)    
        ######################
        return res


    def angle_cos(p0, p1, p2): # ********************************************************************************************************************************* # 
        ######################
        d1, d2 = (p0-p1).astype('float'), (p2-p1).astype('float')
        ######################
        return abs( np.dot(d1, d2) / np.sqrt( np.dot(d1, d1)*np.dot(d2, d2) ) )

    def center_mass(img): # ********************************************************************************************************************************* # 
        ######################
        global squares 
        global xx_pos
    #    global cnt_max
        blur = cv2.GaussianBlur(img, (5, 5), 0)   
        ######################                                   
        for gray in cv2.split(blur):                 
            for thrs in xrange(0, 255, 26): 
                ##############         
                if thrs == 0:
                    bin = cv2.Canny(gray, 0, 50, apertureSize=5)       
                    bin = cv2.dilate(bin, None)                        
                else:
                    retval, bin = cv2.threshold(gray, thrs, 255, cv2.THRESH_BINARY)
                contours, hierarchy = cv2.findContours(bin, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE) 
                ##############
                for cnt in contours:
                    cnt_moment = cnt
                    cnt_len = cv2.arcLength(cnt, True)
                    cnt = cv2.approxPolyDP(cnt, 0.02*cnt_len, True)                                     
                    if len(cnt) == 4 and cv2.contourArea(cnt) > 500: # and cv2.isContourConvex(cnt):   
    #                if cv2.contourArea(cnt) > 1000 and cv2.isContourConvex(cnt):                                                                 
                        cnt = cnt.reshape(-1, 2)
                        max_cos = np.max([angle_cos( cnt[i], cnt[(i+1) % 4], cnt[(i+2) % 4] ) for i in xrange(4)]) 
                        if max_cos < 0.1:   
                            squares.append(cnt)      
                            moments = cv2.moments(cnt_moment) 
                            if moments['m00']!=0:
    #                            cnt_max.append(cnt_moment)
                                cx     = int(moments['m10']/moments['m00']) 
                                xx_pos = cx
                                cy     = int(moments['m01']/moments['m00'])
                                cv2.circle(img,(cx,cy),5,(0,255,0),-1) 
                ############## 
        return img


    def max_cnt(cnt): # ********************************************************************************************************************************* #
        ######################
        cnt_moment = cnt
        cnt_len = cv2.arcLength(cnt, True)
        cnt = cv2.approxPolyDP(cnt, 0.02*cnt_len, True)  
        ######################                                   
        if len(cnt) == 4 and cv2.contourArea(cnt) > 1000 and cv2.isContourConvex(cnt):                                                                                     
            cnt = cnt.reshape(-1, 2)
            max_cos = np.max([angle_cos( cnt[i], cnt[(i+1) % 4], cnt[(i+2) % 4] ) for i in xrange(4)]) 
            if max_cos < 0.1:       
                moments = cv2.moments(cnt_moment) 
                if moments['m00']!=0:
                    cx     = int(moments['m10']/moments['m00']) 
        ######################
        return cx 

    def __init__(self):

        # initialize ROS stuff

        # set publisher and subscriber

        # publisher for pointcloud data.
        # the code for this is not implemented yet.
        # self.line_pub = rospy.Publisher(
        #    'line_data',
        #    sensor_msgs.msg.PointCloud2)

        # publisher for image of line pixels (only for debugging, not used in
        # map)
        self.line_image_pub = rospy.Publisher( self.namespace +
                                              "/" + self.node_name +
                                              self.publisher_image_topic +
                                              '/compressed',
                                              sensor_msgs.msg.CompressedImage,
                                              queue_size=1)

        # self.line_image_pub = rospy.Publisher('line_image',
        #                                       sensor_msgs.msg.Image)

        # this returns the path to the current package
        rospack = rospkg.RosPack()
        self.package_path = rospack.get_path('line_detection')

        if self.use_compressed_format:
        # subscriber for ROS image topic
            self.image_sub = rospy.Subscriber(self.subscriber_image_topic +
                                             "/compressed",
                                              CompressedImage, self.image_callback,
                                              queue_size=1, buff_size=self.buffer_size)
        else:
            # use this for uncompressed raw format
            self.image_sub = rospy.Subscriber(self.subscriber_image_topic,
                                           Image,
                                           self.image_callback, queue_size=1,
                                           buff_size=self.buffer_size)


        self.bridge = CvBridge()

        
        # use this if you need to use the camera_info topic (has intrinsic
        #                                                     parameters)
        # self.camera_info_sub = rospy.Subscriber("/camera/camera_info",
        #                                          CameraInfo,
        #                                          self.camera_info_callback,
        #                                          queue_size=1 )
    
    # this is what gets called when an image is recieved
    def image_callback(self, image):

        # use this to record start time for each frame
        #start_time = time.time()
        

        if(self.use_mono and not self.use_compressed_format and image.encoding != 'mono8'):
            rospy.logerr("image is not mono8! Aborting!")
            return
        
        if self.use_compressed_format:
            #### direct conversion from ROS CompressedImage to CV2 ####
            np_arr = np.fromstring(image.data, np.uint8)
            if self.use_mono:
                img = cv2.imdecode(np_arr, cv2.CV_LOAD_IMAGE_GRAYSCALE)
            else:
                img = cv2.imdecode(np_arr, cv2.CV_LOAD_IMAGE_COLOR)
        else:
            #### direct conversion from ROS Image to CV2 ####
            # first, we need to convert image from sensor_msgs/Image to numpy (or
            # cv2). For this, we use cv_bridge
            try:
                # img = self.bridge.imgmsg_to_cv2(image, "bgr8")
                img = self.bridge.imgmsg_to_cv2(image,
                                                desired_encoding="passthrough")
            except CvBridgeError, e:
                rospy.logerr(e)

        if img is None:
            rospy.logerr("error! img is empty!")
            return

        self.image_height = img.shape[0]
        self.image_width = img.shape[1]

        # if mono, don't take 3rd dimension since there's only one channel
        if self.use_mono:
            roi = img[
            self.roi_top_left_y:self.roi_top_left_y + self.roi_height,
            self.roi_top_left_x:self.roi_top_left_x + self.roi_width,
            ]
        else:
            roi = img[
                self.roi_top_left_y:self.roi_top_left_y + self.roi_height,
                self.roi_top_left_x:self.roi_top_left_x + self.roi_width,
                :
            ]

        # in case roi settings aren't correct, just use the entire image
        if roi.size <= 0:
            rospy.logerr("Incorrect roi settings! Will use the entire image instead!")
            roi = img

        # use entire image as roi (don't cut any parts out)
        # roi = img


        #######################
        frame = roi
        global squares
        global xx_pos
        global cnt_max
        #######################
        frame_b  = color_track(frame, [100, 150, 100], [130, 255, 255])
        frame_r1 = color_track(frame, [  0, 200, 150], [  5, 255, 255])
        frame_r2 = color_track(frame, [169, 200, 150], [179, 255, 255])
        frame_r  = cv2.bitwise_or(frame_r1, frame_r2)
        #######################  
        frame_rr    = center_mass(frame_r)
        squares_red = squares
        red_x       = xx_pos
    #    cnt_max_r   = cnt_max
    #    cv2.drawContours(frame_rr, squares_red, 0, (0, 0, 255), 0 )
        squares     = []
    #    cnt_max     = []
        #######################
        frame_bb     = center_mass(frame_b)
        squares_blue = squares
        blue_x       = xx_pos
    #    cnt_max_b    = cnt_max
    #    cv2.drawContours(frame_bb, squares_blue, 0, (0, 0, 255), 0 )
        squares      = []
    #    cnt_max      = []
        #######################
    #    cnt_max_b.sort()
    #    cnt_max_r.sort()
    #    if cnt_max_b:
    #        cmbm = max(cnt_max_b)
    #        cmb = max_cnt(cmbm)
    #    if cnt_max_r:
    #        cmrm = max(cnt_max_r)
    #        cmr = max_cnt(cmrm)
        #######################
    #    if cnt_max_b and cnt_max_r:
    #        if   cmb > cmr:
    #            cv2.drawContours(frame_rr, squares_red, 0, (0, 0, 255), 0 )
    #            cv2.drawContours(frame_bb, squares_blue, 0, (0, 0, 255), 0 )
    #        elif cmb == cmr:
    #            cv2.drawContours(frame_rr, squares_red, 0, (0, 255, 0), 0 )
    #            cv2.drawContours(frame_bb, squares_blue, 0, (0, 255, 0), 0 )
    #        elif cmb < cmr:
    #            cv2.drawContours(frame_rr, squares_red, 0, (255, 0, 0), 0 )
    #            cv2.drawContours(frame_bb, squares_blue, 0, (255, 0, 0), 0 )
        if   blue_x > red_x:
            cv2.drawContours(frame_rr, squares_red, 0, (0, 0, 255), 0 )
            cv2.drawContours(frame_bb, squares_blue, 0, (0, 0, 255), 0 )
        elif blue_x == red_x:
            cv2.drawContours(frame_rr, squares_red, 0, (0, 255, 0), 0 )
            cv2.drawContours(frame_bb, squares_blue, 0, (0, 255, 0), 0 )
        elif blue_x < red_x:
            cv2.drawContours(frame_rr, squares_red, 0, (255, 0, 0), 0 )
            cv2.drawContours(frame_bb, squares_blue, 0, (255, 0, 0), 0 )
        #######################
        color = cv2.bitwise_or(frame_rr, frame_bb)
        both  = np.hstack((frame,color))
        
        final_image = color

        if lines is not None:
            for x1, y1, x2, y2 in lines[0]:
                cv2.line(final_image, (x1, y1), (x2, y2), 255, self.hough_thickness)

        #### Create CompressedImage to publish ####
        final_image_message = CompressedImage()
        final_image_message.header.stamp = rospy.Time.now()
        final_image_message.format = "jpeg"
        final_image_message.data = np.array(cv2.imencode(
                                            '.jpg',
                                            final_image)[1]).tostring()

        # publishes image message with line pixels in it
        self.line_image_pub.publish(final_image_message)

    ## end image_callback()

    def reconfigure_callback(self, config, level):

        # TODO check if the keys exist in the config dictionary or else error

        self.blur_size = config['blur_size']
        self.hue_low = config['hue_low']
        self.hue_high = config['hue_high']
        self.saturation_low = config['saturation_low']
        self.saturation_high = config['saturation_high']
        self.value_low = config['value_low']
        self.value_high = config['value_high']
        self.backprojection_threshold = config['backprojection_threshold']

        # gabor filter parameters
        self.gabor_ksize = config['gabor_ksize']
        self.gabor_sigma = config['gabor_sigma']
        self.gabor_theta = config['gabor_theta']
        self.gabor_lambda = config['gabor_lambda']
        self.gabor_gamma = config['gabor_gamma']

        self.hough_rho = config['hough_rho']
        self.hough_theta = config['hough_theta']
        self.hough_threshold = config['hough_threshold']
        self.hough_min_line_length = config['hough_min_line_length']
        self.hough_max_line_gap = config['hough_max_line_gap']
        self.hough_thickness = config['hough_thickness']

        self.roi_top_left_x = config['roi_top_left_x']
        self.roi_top_left_y = config['roi_top_left_y']
        self.roi_width = config['roi_width']
        self.roi_height = config['roi_height']

        self.dilate_size = config['dilate_size']
        self.dilate_iterations = config['dilate_iterations']

        self.validate_parameters()

        return config

    # makes sure the parameters are valid and don't crash the
    # openCV calls. Changes them to valid values if invalid.
    def validate_parameters(self):
        
        # these parameters need validation:

        # blur_size can be an odd number only
        if self.blur_size % 2 == 0:
            self.blur_size -= 1

        # hue, saturation, and value parameters cannot have
        # larger or equal low limits than high limits
        if self.hue_low >= self.hue_high:
            self.hue_low = self.hue_high - 1
        if self.saturation_low >= self.saturation_high:
            self.saturation_low = self.saturation_high - 1
        if self.value_low >= self.value_high:
            self.value_low = self.value_high - 1

        # gabor filter parameters don't need validation

        # hough parameters cannot be nonzero
        if self.hough_rho <= 0:
            self.hough_rho = 1
        if self.hough_theta <= 0:
            self.hough_theta = 0.01
        if self.hough_threshold <= 0:
            self.hough_threshold = 1
        if self.hough_min_line_length <= 0:
            self.hough_min_line_length = 1
        if self.hough_max_line_gap <= 0:
            self.hough_max_line_gap = 1

        # now check if ROI parameters are out of bounds
        # only do this if image dimensions have been set
        if self.image_width > 0 and self.image_height > 0:
            if self.roi_width > self.image_width - self.roi_top_left_x:
                self.roi_width = self.image_width - self.roi_top_left_x
            if self.roi_top_left_x < 0:
                self.roi_top_left_x = 0

            if self.roi_height > self.image_height - self.roi_top_left_y:
                self.roi_height = self.image_height - self.roi_top_left_y
            if self.roi_top_left_y < 0:
                self.roi_top_left_y = 0

        if self.dilate_size % 2 == 0:
            self.dilate_size += 1
            rospy.logwarn("dilate_size should not be even! Changed to %d", self.dilate_size)


def main(args):
    # create a line_detection object
    ld = line_detection()

    # start the line_detector node and start listening
    rospy.init_node("line_detection", anonymous=True)

    # starts dynamic_reconfigure server
    srv = Server(LineDetectionConfig, ld.reconfigure_callback)
    rospy.spin()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main(sys.argv)

