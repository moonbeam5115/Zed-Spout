# import library
import sys
import os

sys.path.append('{}/Library/3{}'.format(os.getcwd(), sys.version_info[1]))

import cv2
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import pyzed.sl as sl
import SpoutSDK


def opengl_init(width, height):
    # OpenGL init
    glMatrixMode(GL_PROJECTION)
    glOrtho(0, width, height, 0, 1, -1)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glClearColor(0.0, 0.0, 0.0, 0.0)
    glEnable(GL_TEXTURE_2D)


def pyWindow_init(display):
    # window setup
    pygame.init() 
    pygame.display.set_caption('Spout for Python Webcam Sender Example')
    pygame.display.set_mode(display, DOUBLEBUF|OPENGL)
    pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 10)


def zedCam_init():
    zed = sl.Camera()

    # Create a InitParameters object and set configuration parameters
    init_params = sl.InitParameters()
    init_params.camera_resolution = sl.RESOLUTION.HD720  # Use HD720 video mode
    init_params.depth_mode = sl.DEPTH_MODE.PERFORMANCE
    init_params.coordinate_units = sl.UNIT.METER
    init_params.sdk_verbose = 1

    # Open the camera
    err = zed.open(init_params)
    if err != sl.ERROR_CODE.SUCCESS:
        print("Camera Open : "+repr(err)+". Exit program.")
        exit()

    return zed


def bodyParams_init(cam):
    body_params = sl.BodyTrackingParameters()
    # Different model can be chosen, optimizing the runtime or the accuracy
    body_params.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_FAST
    body_params.enable_tracking = True
    body_params.image_sync = True
    body_params.enable_segmentation = False
    # Optimize the person joints position, requires more computations
    body_params.enable_body_fitting = True

    if body_params.enable_tracking:
        positional_tracking_param = sl.PositionalTrackingParameters()
        # positional_tracking_param.set_as_static = True
        positional_tracking_param.set_floor_as_origin = True
        cam.enable_positional_tracking(positional_tracking_param)

    print("Body tracking: Loading Module...")

    err = cam.enable_body_tracking(body_params)
    if err != sl.ERROR_CODE.SUCCESS:
        print("Enable Body Tracking : "+repr(err)+". Exit program.")
        cam.close()
        exit()
    
    return body_params


def keypoint_extractor(bodies, body_params, body_runtime_param, cam):
    
    _err = cam.retrieve_bodies(bodies, body_runtime_param)
    kps = []
    if bodies.is_new:
        body_array = bodies.body_list
        print(str(len(body_array)) + " Person(s) detected\n")
        if len(body_array) > 0:
            first_body = body_array[0]
            print("First Person attributes:")
            print(" Confidence (" + str(int(first_body.confidence)) + "/100)")
            if body_params.enable_tracking:
                print(" Tracking ID: " + str(int(first_body.id)) + " tracking state: " + repr(
                    first_body.tracking_state) + " / " + repr(first_body.action_state))


            if first_body.mask.is_init():
                print(" 2D mask available")

            keypoint_2d = first_body.keypoint_2d
            for it in keypoint_2d:
                kps.append([it[0], it[1]])
        
    return kps


def drawKeypoints(cam, mat, kps):
    cam.retrieve_image(mat, sl.VIEW.LEFT) # Retrieve left image
    cvImage = mat.get_data() # Convert sl.Mat to cv2.Mat

    # frame = cv2.flip(cvImage, 1 )
    frame = cv2.cvtColor(cvImage, cv2.COLOR_BGR2RGB)

    # Draw keyoints on image
    for point in kps:
        x, y = int(point[0]), int(point[1])
        cv2.circle(frame, (x, y), 5, (0, 0, 255), -1)

    return frame


def spoutSender_init(width, height):
    # init spout sender
    spoutSender = SpoutSDK.SpoutSender()
    # Its signature in c++ looks like this: bool CreateSender(const char *Sendername, unsigned int width, unsigned int height, DWORD dwFormat = 0);
    spoutSender.CreateSender('Spout for Python Webcam Sender Example', width, height, 0)

    return spoutSender


def senderTexture_init(senderTextureID):
    # initalise our sender texture
    glBindTexture(GL_TEXTURE_2D, senderTextureID)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glBindTexture(GL_TEXTURE_2D, 0)


def spoutOpenGL_main(senderTextureID, spoutSender, width, height, frame):
    # Copy the frame from the webcam into the sender texture
    glBindTexture(GL_TEXTURE_2D, senderTextureID)
    glTexImage2D( GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, frame)
    
    # Send texture to Spout
    # Its signature in C++ looks like this: bool SendTexture(GLuint TextureID, GLuint TextureTarget, unsigned int width, unsigned int height, bool bInvert=true, GLuint HostFBO = 0);
    spoutSender.SendTexture(senderTextureID.tolist(), GL_TEXTURE_2D, width, height, False, 0)
    
    # Clear screen
    glClear(GL_COLOR_BUFFER_BIT  | GL_DEPTH_BUFFER_BIT )
    # reset the drawing perspective
    glLoadIdentity()
    
    # Draw texture to screen
    glBegin(GL_QUADS)

    glTexCoord(0,0)        
    glVertex2f(0,0)

    glTexCoord(1,0)
    glVertex2f(width,0)

    glTexCoord(1,1)
    glVertex2f(width,height)

    glTexCoord(0,1)
    glVertex2f(0,height)

    glEnd()

    # update window
    pygame.display.flip()             
    
    # unbind our sender texture
    glBindTexture(GL_TEXTURE_2D, 0)


def main():
    # Create a Camera object
    cam = zedCam_init()

    body_params = bodyParams_init(cam)

    
    bodies = sl.Bodies()
    body_runtime_param = sl.BodyTrackingRuntimeParameters()
    # For outdoor scene or long range, the confidence should be lowered to avoid missing detections (~20-30)
    # For indoor scene or closer range, a higher confidence limits the risk of false positives and increase the precision (~50+)
    body_runtime_param.detection_confidence_threshold = 40
    
    width = 1280
    height = 720
    display = (width,height)

    pyWindow_init(display=display)
    opengl_init(width=width, height=height)

    mat = sl.Mat() 
    # Zed - Body Tracking

    # Spout
    spoutSender = spoutSender_init(width=width, height=height)

    # create texture id for use with Spout
    senderTextureID = glGenTextures(1)
    senderTexture_init(senderTextureID=senderTextureID)

    while(True):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()

        if cam.grab() == sl.ERROR_CODE.SUCCESS:
            
            kps = keypoint_extractor(bodies=bodies,
                                     body_params=body_params,
                                     body_runtime_param=body_runtime_param,
                                     cam=cam)

            frame = drawKeypoints(cam=cam, mat=mat, kps=kps)

            spoutOpenGL_main(senderTextureID=senderTextureID,
                             spoutSender=spoutSender,
                             width=width,
                             height=height,
                             frame=frame) 
        else:
            print("Error during capture : ", err)
            break
    # Close the camera
    cam.disable_body_tracking()
    cam.close()


if __name__ == "__main__":
    main()
