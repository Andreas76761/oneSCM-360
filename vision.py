"""Optional OpenCV preprocessing with unchanged pixel coordinates."""
import io

def prepare(raw,mode):
 from app import Invalid
 if mode not in ['contrast','threshold']:raise Invalid('Unbekannte OpenCV-Vorverarbeitung.')
 try:
  import cv2
  import numpy as np
 except ImportError as exc:raise Invalid('OpenCV fehlt. Unter Windows install-opencv.bat ausführen; alternativ im aktiven Python-Umfeld: python -m pip install -r requirements-opencv.txt') from exc
 from media import read_image
 source=np.asarray(read_image(raw).convert('RGB'))
 gray=cv2.cvtColor(source,cv2.COLOR_RGB2GRAY)
 denoised=cv2.medianBlur(gray,3)
 enhanced=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(denoised)
 output=cv2.adaptiveThreshold(enhanced,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11) if mode=='threshold' else enhanced
 # Geometric transformations deliberately avoided: OCR regions stay in original coordinates.
 edges=cv2.Canny(enhanced,50,150)
 contours,_=cv2.findContours(cv2.dilate(edges,cv2.getStructuringElement(cv2.MORPH_RECT,(9,3))),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 regions=sorted([dict(zip(['x','y','w','h'],map(int,cv2.boundingRect(c)))) for c in contours if cv2.contourArea(c)>=40],key=lambda r:(r['y'],r['x']))[:200]
 ok,encoded=cv2.imencode('.png',output)
 if not ok:raise Invalid('OpenCV konnte das Bild nicht vorbereiten.')
 return encoded.tobytes(),{'engine':'OpenCV '+cv2.__version__,'mode':mode,'width':int(gray.shape[1]),'height':int(gray.shape[0]),'regions':regions,'note':'Konturbereiche sind Strukturhinweise, keine bestätigten Text- oder PII-Bereiche.'}
