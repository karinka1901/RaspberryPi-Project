from machine import ADC, Pin
from piotimer import Piotimer
from fifo import Fifo
import filefifo
import time
import ssd1306
import network
import socket
from time import sleep
import utime
import urequests as requests
import ujson
import math
#-------------------------------------------------------------------------------
i2c = machine.I2C(1, sda=machine.Pin(14), scl=machine.Pin(15))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

samples = Fifo(50)
pin = Pin(26, Pin.OUT)
pulse = ADC(pin)
sample_rate = 250
sample_size = 3500
constant = 1
threshold = 0

#for ppi and calculations
all_values = []
values_above = [] 
peaks = []
collected_ppi = []
values_between = 0
ppi_av = 0
bpm = 0
intervals = []
cleaned_ppi =[]
diffs = []
rmssd = 0


#for menu control
start = True
instr = False
button_push = machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_UP)
menu = True
back_menu = False




#--------MENUS----------------------------------
def start_menu():
    oled.fill(0)
    oled.rect(0, 0, 128, 40, 1)
    oled.text("Stress-B-Gone", 10, 20)
    oled.text("START", 42, 50)
    oled.rect(0, 47, 128, 13, 1)
    oled.show()

def instr_menu():
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    oled.text("Place a finger", 8, 13)
    oled.text("on the sensor", 8, 23)
    oled.text("and press the", 8, 33)
    oled.text("button..", 8, 43)
    oled.show()
    
def menu_results(hr, stress_index,pns_index, sns_index):
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    oled.text("BPM: " + str(hr), 8, 5)
    oled.text("PNS: " + str(pns_index), 8, 20)
    oled.text("SNS:" + str(sns_index), 8, 35)
    oled.text("Stress lvl: " + str(stress_index), 8, 50)
    oled.show()
    
def collecting_menu():
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    oled.text("Collecting data", 5, 20)
    oled.text("Please wait...",5, 40)
    oled.show()
    
def advice_menu(stress_index):
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    if stress_index < 10:
        print("not stressed")
        oled.text("Good job!", 28, 12)
        oled.text("You are not", 20, 27)
        oled.text("stressed!", 28, 42)
        oled.show()
    if stress_index > 15:
        print("too stressed")
        oled.text("Oh no!", 38, 12)
        oled.text("You're stressed!", 2, 27)
        oled.text("Try to relax?", 10, 42)
        oled.show()
    if 10 < stress_index < 15:
        print('just the right amount of stressed')
        oled.text("Just the right", 8, 12)
        oled.text("amount of", 27, 27)
        oled.text("stressed", 28, 42)
        oled.show()
        
def reset(collected_ppi,all_values,peaks):
    collected_ppi.clear()
    all_values.clear()
    peaks.clear()
   

    
#---------------------------BUTTON--------------------------------
def button_fn(pin):
    global start, instr, menu, back_menu, counter
    pushed = False
    if button_push.value() == 0:
        if menu == True:
            if start == True:
                print("in the starting menu")
                instr = True
                sleep(0.1)
                start = False
                oled.fill(0)
                counter = 0
            elif instr == True:
                print("in the instruction menu")
                instr = False
                menu = False
                sleep(0.1)
                oled.fill(0)
                counter = 0
        if menu == False:
            back_menu = True
            exitt = True
            sleep(0.1)
            oled.fill(0)
            oled.show()
        elif not menu and back_menu:
            sleep(0.1)
            menu = True
            start = True
            instr = False
            back_menu = False  
        print(start, instr, menu, back_menu)
        print(button_push.value())

button_push.irq(trigger=machine.Pin.IRQ_FALLING, handler=button_fn)               
            
#---------------------------TIMER-------------------------------------
def read_sample(tid):
    samples.put(pulse.read_u16())
    
timer = Piotimer( mode= Piotimer.PERIODIC, freq = sample_rate, callback = read_sample)

#-------------INTERVALS-------------------------------------------------
def between_peaks(list, peak1, peak2):
    if peak1 not in list or peak2 not in list:
        print("no peaks detected")
    else:
        a = list.index(peak1)
        b = list.index(peak2)
        if a > b:
            a, b = b, a
        return int(b - a)
#----------------------------THRESHOLD-----------------------------------
def calc_threshold(all_values, constant):
    global threshold
    if len(all_values) > 0:
        max_value =max(all_values)
        min_value = min(all_values)
        threshold = ((max_value + min_value)/2) * constant
    else:
        print("no data was collected")
    return threshold
#--------------------------------------PEAKS-------------------------------------
def find_peaks(all_values, threshold):
    peaks = []
    values_above = []

    for i in range(len(all_values)):
        if all_values[i] > threshold:
            values_above.append(all_values[i])
        
        if all_values[i] < threshold and len(values_above) > 0:
            peak_value = max(values_above)
            peaks.append(peak_value)
            values_above.clear()
    return peaks
#------------------------PPI------------------------------------
def calculate_ppi(peaks, all_values):
    collected_ppi = []
    ppi_values = []
    diffs = []
    sum_sq_diff = 0
    global bpm, rmssd, ppi_av

    for i in range(len(peaks)-1):
        values_between = between_peaks(all_values, peaks[i-1], peaks[i])
        
        if values_between >= 0:
            ppi = int((1/250) * values_between * 1000)
            
            if 2000 > ppi > 600:
                ppi_values.append(ppi)

    if len(ppi_values) > 1:
        mean_ppi = sum(ppi_values) / len(ppi_values)
        ppi_dev = math.sqrt(sum([(x - mean_ppi) ** 2 for x in ppi_values]) / (len(ppi_values) - 1))
        collected_ppi = [x for x in ppi_values if abs(x - mean_ppi) <= 3 * ppi_dev]

        if len(collected_ppi) > 0:
            ppi_av = sum(collected_ppi)/len(collected_ppi)
            bpm = int(60 / (ppi_av/1000))
            
            diffs = [collected_ppi[i] - collected_ppi[i-1] for i in range(1, len(collected_ppi))]
            for diff in diffs:
                sum_sq_diff +=diff**2
            rmssd = int(math.sqrt(sum_sq_diff / len(diffs)))
            
        else:
            ppi_av = None
            bpm = None
            rmssd = None
            print("Try again")
        
    return ppi_av, bpm, collected_ppi, rmssd



#-----------------------------------------------MAIN---------------------------------------------
while True:  
    while menu:
        if start:
            oled.fill(0)
            start_menu()
        elif instr:
            oled.fill(0)
            instr_menu()
        elif not instr and not start:
            oled.fill(0)
            break
        
    while not menu:
        collecting_menu()

        while len(all_values) < sample_size:
            if not samples.empty():
                value = samples.get()
          
                if value > 30000:
                    all_values.append(value)
                    
                    

        threshold = calc_threshold(all_values, constant)
        peaks = find_peaks(all_values, threshold)
        ppi_av, bpm, collected_ppi, rmssd = calculate_ppi(peaks, all_values)


           
        ##################################testing#############################################
        print("collected values ", all_values)
        print("sample size: ", sample_size)                
        print("threshold: ", threshold)                       
        print("peaks: ", peaks)
        print(" av ppi:", ppi_av)
        print("collected ppi: ", collected_ppi)
        print("bpm :",  bpm)
        print("hrv :", rmssd)

        if bpm < 50:
            oled.fill(0)
            oled.text("BPM:" + str(bpm), 5, 10)
            oled.text("HRV:" + str(rmssd), 60, 10)
            oled.text("Something", 5, 22)
            oled.text("is wrong..", 5, 32)
            oled.text("Try again!", 5, 42)
            oled.show()
            sleep(5)
            reset(collected_ppi,all_values,peaks)
            menu = True
            start = True
            break 

            
#--------------------------------------------------KUBIOS------------------------------------------------------
        if len(collected_ppi) > 10: 
            ssid = 'kme511group206'
            password = 'kme511group206'

            oled.fill(0)

            def connect():
                #Connect to WLAN
                wlan = network.WLAN(network.STA_IF)
                wlan.active(True)
                wlan.connect(ssid, password)
                while wlan.isconnected() == False:
                    oled.text('Waiting for ', 0, 10)
                    oled.text('connection...', 0, 20)
                    oled.show()
                    oled.fill(0)
                    sleep(1)
                ip = wlan.ifconfig()[0]
                return ip
            try:
                ip = connect()
            except KeyboardInterrupt:
                machine.reset()

            APIKEY = "pbZRUi49X48I56oL1Lq8y8NDjq6rPfzX3AQeNo3a"
            CLIENT_ID = "3pjgjdmamlj759te85icf0lucv"
            CLIENT_SECRET = "111fqsli1eo7mejcrlffbklvftcnfl4keoadrdv1o45vt9pndlef"
            LOGIN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/login"
            TOKEN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/oauth2/token"
            REDIRECT_URI = "https://analysis.kubioscloud.com/v1/portal/login"

            oled.fill(0)
            oled.rect(0, 0, 128, 64, 1)
            oled.text("Analyzing data", 8, 20)
            oled.text("Please wait...",8, 40)
            oled.show()

            response = requests.post(
            url = TOKEN_URL,
            data = 'grant_type=client_credentials&client_id={}'.format(CLIENT_ID),
            headers = {'Content-Type':'application/x-www-form-urlencoded'},
            auth = (CLIENT_ID, CLIENT_SECRET))

            response = response.json()
            access_token = response["access_token"]

            data_set = {
            "type": "RRI",
            "data": collected_ppi,
            "analysis": { "type": "readiness"}
            }

            try:
                response = requests.post(
                    url = "https://analysis.kubioscloud.com/v2/analytics/analyze",
                    headers = { "Authorization": "Bearer {}".format(access_token), "X-Api-Key": APIKEY },
                    json = data_set)
                response = response.json()
            except OSError as e:
                if e.args[0] == -2:
                    print("Error: Network connection failed.")
                    break
                else:
                    print("Error:", e)
                    

            #print(response) #test

            pns_index = (response["analysis"]["pns_index"])
            sns_index = (response["analysis"]["sns_index"])
            stress_index = round(response["analysis"]["stress_index"])
            hr = round(response["analysis"]["mean_hr_bpm"])
         
            menu_results(hr, stress_index,pns_index, sns_index)
            sleep(10)
            advice_menu(stress_index)
            sleep(5)
            reset(collected_ppi,all_values,peaks)
            menu = True
            start = True
            break
            
        else:
            oled.fill(0)
            oled.rect(0, 0, 128, 64, 1)
            oled.text("BPM:" + str(bpm), 5, 10)
            oled.text("HRV:" + str(rmssd), 60, 10)
            oled.text("Not enough", 5, 22)
            oled.text("collected data", 5, 32)
            oled.text("Try again!", 5, 42)
            oled.show()
            sleep(5)
            reset(collected_ppi,all_values,peaks)
            menu = True
            start = True
            break   
