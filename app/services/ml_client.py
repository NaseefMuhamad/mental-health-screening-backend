"""Loopback inference bridge. Browser requests never supply model results."""
import json,os,urllib.request,urllib.error
from urllib.parse import urlparse
from app.services.errors import DependencyUnavailable,InvalidOperation

def predict(inputs):
    base=os.getenv('ML_SERVICE_URL','http://127.0.0.1:8010').rstrip('/')
    parsed=urlparse(base)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username or parsed.password or parsed.path not in {'','/'}:raise DependencyUnavailable('Configure the local ML inference service URL.')
    request=urllib.request.Request(base+'/predict',data=json.dumps(inputs,allow_nan=False).encode(),method='POST',headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=10) as response:
            raw=response.read(65537)
            if len(raw)>65536:raise ValueError('Unexpected response size')
            data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('Unexpected response structure')
        if data.get('contract_version')!='student-wellbeing-demo-v1':raise ValueError('Contract mismatch')
        for key in ['stress','anxiety']:
            if data[key]['level'] not in {'Low','Medium','High'}:raise ValueError('Invalid category')
        if not isinstance(data.get('model_version'),str) or not 1<=len(data['model_version'])<=120:raise ValueError('Invalid model version')
        return data
    except urllib.error.HTTPError as error:
        if error.code==422:raise InvalidOperation('Inputs are outside the demo model support or course/year mapping. Check the assessment and model documentation.') from None
        raise DependencyUnavailable('ML inference is unavailable. Start the trained model service.') from None
    except (OSError,ValueError,KeyError,TypeError):raise DependencyUnavailable('ML inference is unavailable. Train the models and start the local model service.') from None
