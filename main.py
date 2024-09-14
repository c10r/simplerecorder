import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QRadioButton, QButtonGroup, QCheckBox
import sys
import subprocess

class ScreenRecorder(QWidget):
    def __init__(self):
        super().__init__()

        Gst.init(None)
        self.pipeline = None  # To store the GStreamer pipeline
        self.window_id = None  # To store the selected window ID
        self.initUI()

    def initUI(self):
        # Create radio buttons for "Entire Screen" and "Specific Window"
        self.entireScreenButton = QRadioButton('Entire Screen')
        self.specificWindowButton = QRadioButton('Specific Window')
        self.entireScreenButton.setChecked(True)  # Default selection

        # Create a checkbox for microphone input
        self.audioCheckBox = QCheckBox('Enable Microphone Input')
        self.audioCheckBox.setChecked(False)  # Default is unchecked

        # Group the radio buttons
        self.radioGroup = QButtonGroup()
        self.radioGroup.addButton(self.entireScreenButton)
        self.radioGroup.addButton(self.specificWindowButton)

        # Create Start and Stop buttons
        self.startButton = QPushButton('Start Recording', self)
        self.stopButton = QPushButton('Stop Recording', self)
        self.stopButton.setEnabled(False)  # Disable Stop button initially

        # Connect buttons to their functions
        self.startButton.clicked.connect(self.startRecording)
        self.stopButton.clicked.connect(self.stopRecording)

        # Set up the layout
        layout = QVBoxLayout()
        layout.addWidget(self.entireScreenButton)
        layout.addWidget(self.specificWindowButton)
        layout.addWidget(self.audioCheckBox)
        layout.addWidget(self.startButton)
        layout.addWidget(self.stopButton)
        self.setLayout(layout)

        self.setWindowTitle('Screen Recorder')
        self.show()
    
    def startRecording(self):
        self.pipeline = Gst.Pipeline.new("screen-audio-recording")

        # Build the GStreamer pipeline based on selection
        ximagesrc = Gst.ElementFactory.make("ximagesrc", "ximagesrc")
        ximagesrc.set_property("use-damage", True)

        if self.specificWindowButton.isChecked():
            self.window_id = self.selectWindow()
            if not self.window_id:
                print("No window selected.")
                self.stopRecording()
                return  # User cancelled or failed to select a window
            ximagesrc.set_property("xid", int(self.window_id))

        # Create video elements
        videoscale = Gst.ElementFactory.make("videoscale", "videoscale")
        videoconvert = Gst.ElementFactory.make("videoconvert", "videoconvert")
        x264enc = Gst.ElementFactory.make("x264enc", "x264enc")
        video_queue = Gst.ElementFactory.make("queue", "video_queue")

        # Create audio elements
        if self.audioCheckBox.isChecked():
            pulsesrc = Gst.ElementFactory.make("pulsesrc", "pulsesrc")
            audioconvert = Gst.ElementFactory.make("audioconvert", "audioconvert")
            voaacenc = Gst.ElementFactory.make("voaacenc", "voaacenc")
            audio_queue = Gst.ElementFactory.make("queue", "audio_queue")

        # Create muxer and sink
        mp4mux = Gst.ElementFactory.make("mp4mux", "mp4mux")
        filesink = Gst.ElementFactory.make("filesink", "filesink")

        # Check all elements are created
        if not all([ximagesrc, videoscale, videoconvert, x264enc, video_queue, mp4mux, filesink]):
            print("Failed to create GStreamer elements.")
            sys.exit(1)

        if self.audioCheckBox.isChecked():
            if not all([pulsesrc, audioconvert, voaacenc, audio_queue]):
                print("Failed to create GStreamer audio elements.")
                sys.exit(1)

        # Set element properties
        ximagesrc.set_property("use-damage", 1)
        videoscale.set_property("method", 0)
        x264enc.set_property("tune", "zerolatency")
        filesink.set_property("location", "output.mp4")

        # Create caps
        caps1 = Gst.Caps.from_string("video/x-raw,framerate=30/1")
        caps2 = Gst.Caps.from_string("video/x-raw")
        caps3 = Gst.Caps.from_string("video/x-raw,format=I420")

        # Add elements to the pipeline
        for elem in [ximagesrc, videoscale, videoconvert, x264enc, video_queue]:
            self.pipeline.add(elem)

        if self.audioCheckBox.isChecked():
            for elem in [pulsesrc, audioconvert, voaacenc, audio_queue]:
                self.pipeline.add(elem)

        for elem in [mp4mux, filesink]:
            self.pipeline.add(elem)

        # Link video elements with caps
        if not ximagesrc.link_filtered(videoscale, caps1):
            print("Failed to link ximagesrc to videoscale with caps.")
            sys.exit(1)
        if not videoscale.link_filtered(videoconvert, caps2):
            print("Failed to link videoscale to videoconvert with caps.")
            sys.exit(1)
        if not videoconvert.link_filtered(x264enc, caps3):
            print("Failed to link videoconvert to x264enc with caps.")
            sys.exit(1)
        if not x264enc.link(video_queue):
            print("Failed to link x264enc to video_queue.")
            sys.exit(1)

        # Link audio elements
        if self.audioCheckBox.isChecked():
            if not pulsesrc.link(audioconvert):
                print("Failed to link pulsesrc to audioconvert.")
                sys.exit(1)
            if not audioconvert.link(voaacenc):
                print("Failed to link audioconvert to voaacenc.")
                sys.exit(1)
            if not voaacenc.link(audio_queue):
                print("Failed to link voaacenc to audio_queue.")
                sys.exit(1)

        # Request video pad from mp4mux
        video_pad_template = mp4mux.get_pad_template("video_%u")
        video_pad = mp4mux.request_pad(video_pad_template, None, None)
        if not video_pad:
            print("Failed to get video pad from mp4mux.")
            sys.exit(1)

        # Get the src pad from video_queue
        video_queue_src_pad = video_queue.get_static_pad("src")
        if not video_queue_src_pad:
            print("Failed to get src pad from video_queue.")
            sys.exit(1)

        # Link video_queue src pad to mp4mux video sink pad
        if video_queue_src_pad.link(video_pad) != Gst.PadLinkReturn.OK:
            print("Failed to link video_queue to mp4mux.")
            sys.exit(1)

        if self.audioCheckBox.isChecked():
            # Request audio pad from mp4mux
            audio_pad_template = mp4mux.get_pad_template("audio_%u")
            audio_pad = mp4mux.request_pad(audio_pad_template, None, None)
            if not audio_pad:
                print("Failed to get audio pad from mp4mux.")
                sys.exit(1)

            # Get the src pad from audio_queue
            audio_queue_src_pad = audio_queue.get_static_pad("src")
            if not audio_queue_src_pad:
                print("Failed to get src pad from audio_queue.")
                sys.exit(1)

            # Link audio_queue src pad to mp4mux audio sink pad
            if audio_queue_src_pad.link(audio_pad) != Gst.PadLinkReturn.OK:
                print("Failed to link audio_queue to mp4mux.")
                sys.exit(1)

        # Link muxer to filesink
        if not mp4mux.link(filesink):
            print("Failed to link mp4mux to filesink.")
            sys.exit(1)

        # Start the pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set the pipeline to the playing state.")
            self.pipeline.set_state(Gst.State.NULL)
            return

        self.startButton.setEnabled(False)
        self.stopButton.setEnabled(True)

    def selectWindow(self):
        try:
            # Run xwininfo to get the window ID
            result = subprocess.run(
                ['xwininfo', '-int'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                print("Error running xwininfo")
                return None
            output = result.stdout
            # Parse the window ID from the output
            for line in output.splitlines():
                if "Window id:" in line:
                    window_id = line.split()[3]
                    print(f"Selected window ID: {window_id}")
                    return window_id
            print("Window ID not found")
            return None
        except Exception as e:
            print(f"Error selecting window: {e}")
            return None

    def stopRecording(self):
        if self.pipeline:
            # Send EOS event to the pipeline
            self.pipeline.send_event(Gst.Event.new_eos())

            # Wait for EOS message
            bus = self.pipeline.get_bus()
            # Wait until we receive an EOS or ERROR message
            while True:
                msg = bus.timed_pop_filtered(
                    Gst.CLOCK_TIME_NONE,
                    Gst.MessageType.EOS | Gst.MessageType.ERROR
                )
                if msg:
                    t = msg.type
                    if t == Gst.MessageType.EOS:
                        print("End-Of-Stream reached.")
                        break
                    elif t == Gst.MessageType.ERROR:
                        err, debug = msg.parse_error()
                        print(
                            f"Error received from element {msg.src.get_name()}: {err.message}")
                        print(
                            f"Debugging information: {debug if debug else 'None'}")
                        break
                else:
                    break  # No more messages

            # Set pipeline state to NULL after processing EOS
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        self.startButton.setEnabled(True)
        self.stopButton.setEnabled(False)

    def closeEvent(self, event):
        # Ensure the gst-launch process is terminated when the app is closed
        if self.pipeline:
            self.stop_recording()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    recorder = ScreenRecorder()
    sys.exit(app.exec_())
