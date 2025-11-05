import pvporcupine
import pyaudio
import struct
import pyttsx3
import speech_recognition as sr
import cv2
import requests
import os
import threading
import time


# ==================================================
# SETTINGS –– CHANGE THESE ONLY
# ==================================================
ACCESS_KEY = ""   # Private Picovoice key
WAKE_WORD_FILE = r""                        # path to my .ppn file , private
GEMINI_API_KEY = ""                # my Gemini key , removing for privacy concern
# ==================================================


# ------------------ GLOBALS ------------------
stop_event = threading.Event()   # safer thread flag
speaking_thread = None           # thread handle for speech


# ==================================================
#  Voice Output (threaded + interruptible)
# ==================================================
def speak(text):
    """Speaks text in a separate thread that can be stopped with stop_event."""
    def _speak():
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[1].id)  # female voice
        engine.setProperty('rate', 200)
        engine.say(text)

        while True:
            if stop_event.is_set():
                engine.stop()
                print("Speech stopped early.")
                break
            engine.runAndWait()
            break
        engine.stop()

    global speaking_thread
    speaking_thread = threading.Thread(target=_speak, daemon=True)
    speaking_thread.start()


# ==================================================
#  Listen for user command
# ==================================================
def listen_for_command(timeout=5, phrase_time_limit=6):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening for your command...")
        r.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            print("Recognizing...")
            cmd = r.recognize_google(audio).lower()
            print(f"You said: {cmd}")
            return cmd
        except sr.WaitTimeoutError:
            print("No command detected.")
        except sr.UnknownValueError:
            print("Could not understand audio.")
        except Exception as e:
            print(f"Error: {e}")
    return ""


# ==================================================
#  Camera Control
# ==================================================
def open_camera():
    speak("Opening camera.")
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        speak("Sorry, I cannot access the camera.")
        return
    speak("Camera is on. Press Q to exit.")
    while True:
        ret, frame = cam.read()
        if not ret:
            break
        cv2.imshow("Robo Cam", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cam.release()
    cv2.destroyAllWindows()
    speak("Camera closed.")


# ==================================================
#  Volume
# ==================================================
import pyautogui
import time

def change_volume(direction):
    try:
        if direction == "up":
            for _ in range(5):  # each press ≈ 2%
                pyautogui.press("volumeup")
                time.sleep(0.05)
            speak("Volume increased.")
            print("Volume Up (keyboard method)")

        elif direction == "down":
            for _ in range(5):
                pyautogui.press("volumedown")
                time.sleep(0.05)
            speak("Volume decreased.")
            print("Volume Decreased to 60")

    except Exception as e:
        print("Volume control error:", e)
        speak("Sorry, I couldn't change the volume.")



# ==================================================
#  Gemini API
# ==================================================
def call_gemini_api(prompt):
    try:
        #  Confirmed working endpoint (Gemini 2.5 Flash)
        url = "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": GEMINI_API_KEY}
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ]
        }

        print("...")
        resp = requests.post(url, headers=headers, params=params, json=data)

        if resp.status_code == 200:
            result = resp.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            print(text)
            return text
        else:
            print(" API error:", resp.text)
            return "Sorry, I couldn’t get an answer from Gemini."

    except Exception as e:
        print("Gemini error:", e)
        return "I faced a problem connecting to Gemini."


# ==================================================
#  Wake-word Initialization
# ==================================================
porcupine = pvporcupine.create(
    access_key=ACCESS_KEY,
    keyword_paths=[WAKE_WORD_FILE]
)

pa = pyaudio.PyAudio()
audio_stream = pa.open(
    rate=porcupine.sample_rate,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    frames_per_buffer=porcupine.frame_length
)

print("Listening for wake word: 'Hey Robo' ...")


# ==================================================
# ==================================================
#  Main Loop
# ==================================================
is_listening = False  # flag to prevent listening during speech

try:
    while True:
        pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
        pcm_unpacked = struct.unpack_from("h" * porcupine.frame_length, pcm)
        keyword_index = porcupine.process(pcm_unpacked)

        if keyword_index >= 0:
            # stop any ongoing speech first
            stop_event.set()
            time.sleep(0.25)
            stop_event.clear()

            print("Wake word detected: Hey Robo")

            # if it was mid-speaking, interrupt immediately
            if speaking_thread and speaking_thread.is_alive():
                print("Interrupted speech.")
                continue  # go back to listening for next wake word

            # greet the user
            is_listening = False
            speak("Hello, what can I do for you?")
            if speaking_thread is not None:
                speaking_thread.join()  # only wait for short greeting

            # now start listening
            is_listening = True
            command = listen_for_command()

            if "camera" in command:
                open_camera()
            elif "volume up" in command:
                change_volume("up")
            elif "volume down" in command:
                change_volume("down")
            elif command:
                is_listening = False
                answer = call_gemini_api(command)
                speak(answer)
            else:
                speak("I did not hear any command. Please try again.")
                if speaking_thread is not None:
                    speaking_thread.join()
                is_listening = True

except KeyboardInterrupt:
    print("Stopping...")

finally:
    if audio_stream:
        audio_stream.close()
    pa.terminate()
    porcupine.delete()

