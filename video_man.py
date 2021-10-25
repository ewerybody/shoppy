import os
import time
from io import StringIO

from pyside import QtCore


ARGS = '-f gdigrab -draw_mouse {pointer} -framerate {fps} -offset_x {x} -offset_y {y} -video_size {w}x{h} -show_region 0 -i desktop -b:v {quality}k'
TMP_NAME = '_kiekste_tmp'
TMP_PATH = os.path.join(os.getenv('TEMP', ''), TMP_NAME)


class VideoMan(QtCore.QObject):
    video_found = QtCore.Signal()
    capture_stopped = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.path = ''
        self.thread = None  # type: _CaptureThread | None
        QtCore.QTimer(self).singleShot(500, self._find_ffmpeg)

    def _find_ffmpeg(self):
        thread = _FFMPegFinder(self)
        thread.found.connect(self._ffmpeg_found)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _ffmpeg_found(self, path: str):
        if not os.path.isfile(path):
            return
        self.path = path
        self.video_found.emit()

    def capture(self, rect: QtCore.QRectF):
        import uuid

        os.makedirs(TMP_PATH, exist_ok=True)
        out_file = os.path.join(TMP_PATH, f'_tmp_video{uuid.uuid4()}.mp4')
        if os.path.isfile(out_file):
            os.unlink(out_file)

        settings = self.parent().settings
        capture_settings = {
            'x': rect.x(), 'y': rect.y(),
            'w': rect.width(), 'h': rect.height(),
            'fps': settings.video_fps,
            'quality': settings.video_quality,
            'pointer': int(settings.draw_pointer),
            'out_path': out_file,
        }

        # _run_video_process(self.path, capture_settings)

        self.thread = _CaptureThread(self, self.path, capture_settings)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._stopped)
        self.thread.start()

    def stop(self):
        if self.thread is None:
            return
        self.thread.stop()

    def _stopped(self):
        self.capture_stopped.emit()
        print('self.thread finished: %s' % self.thread)
        self.thread


class _CaptureThread(QtCore.QThread):
    progress = QtCore.Signal(dict)

    def __init__(self, parent, path, settings):
        super().__init__(parent)

        self.path = path
        self.settings = settings

        # how to deal with output? Do we need it?
        # subprocess needs file like objs to pipe to. These also need `.fileno`
        # so StringIO doesn't do! :/ We could open real files to pipe to:
        # self._strout_file = os.path.join(TMP_PATH, '_tmpout')
        # self._strerr_file = os.path.join(TMP_PATH, '_tmperr')

    def stop(self):
        self.requestInterruption()

    def _stdout(self, things):
        print('_stdout: %s' % things)

    def _stderr(self, things):
        print('_stdout: %s' % things)

    def run(self):
        # I'd love to use `QProcess` right away but had massive problems so far.
        # process = QtCore.QProcess()
        # process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        import subprocess, signal

        args_list = [self.path]
        args_list.extend(ARGS.format_map(self.settings).split())
        args_list.append(self.settings['out_path'])
        print('running _CaptureThread with args:\n%s' % args_list)

        try:
            process = subprocess.Popen(args_list)

            while True:
                if self.isInterruptionRequested():
                    process.send_signal(signal.CTRL_C_EVENT)
                    break
                self.msleep(100)

            print('process: %s' % process)
        except KeyboardInterrupt:
            print('process interrupted')
            pass


class _OutputPipe(StringIO):
    def __init__(self, func):
        self._write_to = func

    def write(self, msg):
        self._write_to(msg)

    def fileno(self):
        return 1337


def _run_video_process(path, settings):
    import subprocess

    args_list = [path]
    args_list.extend(ARGS.format_map(settings).split())
    args_list.append(settings['out_path'])
    print('args: %s' % args_list)

    process = subprocess.Popen(args_list)
    print('process: %s' % process)
    process

    # print('things: %s' % str(things))
    while True:
        # if self.isInterruptionRequested():
        #     process.close()
        output = process.readAll()
        if output:
            print('process output: %s' % output)
        error = process.errorString()
        if error:
            print('process error: %s' % error)
        self.msleep(100)

    time.sleep(0.1)


class _FFMPegFinder(QtCore.QThread):
    found = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

    def run(self):
        found = _find_ffmpeg()
        if found:
            self.found.emit(found)


def _find_ffmpeg():
    import subprocess

    nfo = subprocess.STARTUPINFO()
    nfo.wShowWindow = subprocess.SW_HIDE
    nfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        found = subprocess.check_output(['where', 'ffmpeg'], startupinfo=nfo)
        return found.decode().strip()
    except subprocess.CalledProcessError:
        return ''