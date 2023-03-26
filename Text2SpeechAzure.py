import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.cognitiveservices.speech import SpeechSynthesisOutputFormat
from azure.identity import DefaultAzureCredential
from datetime import datetime
import os
import pysilk

class Text2Speech:
    def __init__(self, speech_key, service_region, container_name, connect_str, error_url, set_speech_synthesis_output_format=SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm, Dir='./SpeechResources/', error_audio='error.silk'):
        self.speech_key = speech_key
        self.service_region = service_region
        self.container_name = container_name
        self.connect_str = connect_str
        self.error_url = error_url
        self.set_speech_synthesis_output_format = set_speech_synthesis_output_format
        self.dir = Dir
        self.error_audio = Dir + error_audio
        self.file_dir = ""
        self.file_name = ""
    def getVoice(self, text):
        if text == None or text == "":
            return self.error_audio
        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
        speech_config.set_speech_synthesis_output_format(self.set_speech_synthesis_output_format)
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

        ssml = """
                <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
                       xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">
                    <voice name="zh-CN-XiaoyiNeural">
                        <mstts:express-as role="Girl" style="disgruntled" styledegree="5">
                            <prosody contour="(60%,-60%) (100%,+80%)">
                            """ + text + """
                            </prosody>
                        </mstts:express-as>
                    </voice>
                </speak>
                """
        result = speech_synthesizer.speak_ssml_async(ssml).get()
        audio_name = "Audio" + datetime.now().strftime("%Y%m%d%H%M%S")
        with open(self.dir + audio_name + ".pcm", 'wb') as audio_file:
            audio_file.write(result.audio_data)
        #convert from pcm to silk
        with open(self.dir + audio_name + ".pcm", "rb") as pcm, open(self.dir + audio_name + ".silk", "wb") as silk:
            pysilk.encode(pcm, silk, 24000, 24000)

        # Checks result.
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("Speech synthesized to speaker for text [{}]".format(text))
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print("Speech synthesis canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    print("Error details: {}".format(cancellation_details.error_details))
            print("Did you update the subscription info?")
        audio_name = audio_name + ".silk"
        self.file_dir = self.dir + audio_name
        self.file_name = audio_name
        if os.path.exists(self.dir + audio_name):
            return self.dir + audio_name, audio_name
        else:
            return self.error_audio, "error.silk"
    def upload(self, file_dir=None, file_name=None):
        blob_service_client = BlobServiceClient.from_connection_string(self.connect_str)
        blob_client = blob_service_client.get_blob_client(container=self.container_name, blob=self.file_name)
        with open(file=self.file_dir, mode="rb") as data:
            result = blob_client.upload_blob(data)
            # blob_client.get_blob_properties()
            # print(result)
            # print(blob_client.url)
        return blob_client.url

if __name__ == "__main__":
    voice = Text2Speech("08187d00705f4504a381f056ea7868ce", "eastasia", "speechresources", "DefaultEndpointsProtocol=https;AccountName=seegabotvoice;AccountKey=+b1cG6ApYnZNydeW/f5qItZk4gSjeJ+jbJcV5dic0dgDjOEAsrOrvZJMTZklTzW4K8uO1aFQpRVm+AStYpBSTQ==;EndpointSuffix=core.windows.net", "https://seegabotvoice.blob.core.windows.net/speechresources/error.mp3")
    file_dir, file_name = voice.getVoice("哎呀，我想说的话不见啦！")
    voice.upload()
