from machine import Pin             # Import Pin class from machine module
from onewire import OneWire         # Import OneWire class from onewire module
from ds18x20 import DS18X20         # Import DS18X20 class from ds18x20 module
from neopixel import NeoPixel       # Import NeoPixel class from neopixel module
import _thread                      # Import _thread module
import usocket                      # Import usocket module
import math                         # Import math module
import time                         # Import time module
import socket                       # Import socket module
import network                      # Import network module
import select                       # Import select module
import json                         # Import json module
import binascii                     # Import binascii module


# List of ports where DS18X20 devices are connected
ds18x20_ports = [1, 2, 3, 10, 11]

class WS2812B:
    def __init__(self, port, num_leds, color=(255, 255, 255)):
        self.np = NeoPixel(Pin(port), num_leds)
        self.pulsating = False
        self.t = 0
        self.color = color
        
    def set_color(self, led_index, color):
        self.np[led_index] = color
        self.np.write()

    def clear(self):
        for i in range(len(self.np)):
            self.np[i] = (0, 0, 0)
        self.np.write()

    def start_pulsating(self, colorRGB, start_intensity=0, stop_intensity=255, frequency=1):
        self.pulsating = True
        self.start_intensity = start_intensity
        self.stop_intensity = stop_intensity
        self.delay = 1.0 / (frequency * 360)  # Calculate delay based on frequency
        self.pulse_color = colorRGB
        _thread.start_new_thread(self._pulsate, ())

    def stop_pulsating(self):
        self.pulsating = False

    def _pulsate(self):
        last_intensity = None
        while self.pulsating:
            for i in range(0, 360):  # Loop over degrees in a circle
                intensity = int((math.sin(math.radians(i)) + 1) / 2 * (self.stop_intensity - self.start_intensity) + self.start_intensity)
                #print("Intensity: ", intensity)
                time.sleep(self.delay)  # Use calculated delay
                if last_intensity != intensity:
                    self.set_color(0, tuple(intensity * x // 255 for x in self.pulse_color))
                last_intensity = intensity

class DS18x20:
    def __init__(self, ports):
        self.devices = []
        for port in ports:
            ow = OneWire(Pin(port))
            ds = DS18X20(ow)
            self.devices.extend([(port, device) for device in ds.scan()])
        self.temps = []
        self.thread = None
        
    def start(self):
        if self.thread is None:
            self.thread = _thread.start_new_thread(self.print_to_console, ())

    def scan_devices(self):
        #print("Scanning for DS18x20 devices")
        #print("Devices found: ", self.devices)
        return self.devices

    def read_temperatures(self):
        temps = []
        for port, device in self.devices:
            ow = OneWire(Pin(port))
            ds = DS18X20(ow)
            ds.convert_temp()
            time.sleep_ms(750)
            temps.append({
                "serial": "0x" + binascii.hexlify(device).decode(),
                "port": port,
                "temp": "{:.2f}".format(ds.read_temp(device))
            })
        return temps

    def update_temps(self):
        self.temps = self.read_temperatures()
            
    def get_temperatures(self):
        return json.dumps(self.temps)
    
    def print_to_console(self):
        old_data = None
        while True:
            self.update_temps()
            data = self.get_temperatures()
            if data != old_data:
                print(data)
            old_data = data
            time.sleep(1)
            
    def start_socket_server(self, host, port):
        self.server_socket = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        self.server_socket.bind((host, port))
        self.server_socket.listen(5)
        for i in range(5):  # Create 5 threads to handle connections
            _thread.start_new_thread(self._handle_connections, ())
        
    def _handle_connections(self):
        while True:
            client_socket, addr = self.server_socket.accept()
            print('Connected by', addr)
            old_data = None
            try:
                while True:
                    self.update_temps()  # Update the temperatures
                    data = self.get_temperatures()
                    if data != old_data:
                        client_socket.sendall((data + '\n\r').encode())  # Append a newline character to the data
                        old_data = data
                    time.sleep(1)  # Wait for 1 second
            except Exception as e:
                print('Error handling connection:', e)
                client_socket.close()  # Close the client socket when an error occurs

class WiFiConnection:
    def __init__(self, ssid, password):
        self.ssid = ssid
        self.password = password
        self.sta_if = network.WLAN(network.STA_IF)

    def connect(self):
        if not self.sta_if.isconnected():
            print('connecting to network...')
            self.sta_if.active(True)
            self.sta_if.connect(self.ssid, self.password)
            while not self.sta_if.isconnected():
                pass
        print('network config:', self.sta_if.ifconfig())

class WebServer:
    def __init__(self, port=80):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(('', port))
        self.socket.listen(5)
        self.socket.setblocking(False)
        self.inputs = [self.socket]
        
    def serve(self):
        _thread.start_new_thread(self.webserver, ())

    def webserver(self):
        while True:
            readable, _, _ = select.select(self.inputs, [], [])
            for s in readable:
                if s is self.socket:
                    conn, addr = self.socket.accept()
                    print('Got a connection from %s' % str(addr))
                    conn.setblocking(False)
                    self.inputs.append(conn)
                else:
                    request = s.recv(1024)
                    if request:
                        print('Content = %s' % str(request))
                        # Send HTTP response
                        response_body = """
                                        <html>
                                        <body>
                                        <h1>ESP32C6 running micropython for wirless probes!</h1>
                                        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/3/34/INFICON-Corporate-Logo-2-Color.png/1200px-INFICON-Corporate-Logo-2-Color.png" alt="LOGO">
                                        </body>
                                        </html>
                                        """
                        response_headers = {
                            'Content-Type': 'text/html',
                            'Content-Length': len(response_body),
                        }

                        response = "HTTP/1.1 200 OK\r\n"

                        for header, value in response_headers.items():
                            response += f"{header}: {value}\r\n"

                        response += "\r\n" + response_body

                        s.send(response.encode())
                    else:
                        s.close()
                        self.inputs.remove(s)


# Main function 
def main():
    # Create an instance of WS2812B class with red color and start intensity 0 and stop intensity 10
    ws2812b = WS2812B(8, 1, (0, 255, 0))  # Assuming the strip is connected to port 8 and has 1 LED
    
    # Start pulsating the first LED
    ws2812b.start_pulsating(colorRGB=(0,255,0), start_intensity=5, stop_intensity=25, frequency=0.5)
 
    # Connect to WiFi network
    wifi_connection = WiFiConnection('xxx', 'yyy')
    wifi_connection.connect()
    
    print("Starting web server")

    # Create and start the web server
    web_server = WebServer()
    #web_server.serve()
    
    print("Starting DS18x20 sensor")
    
     # Initialize sensor class with the list of ports where DS18X20 devices are connected
    sensor = DS18x20(ds18x20_ports)  
    sensor.scan_devices()

    # Start the sensor data collection and printing to console
    sensor.start()
    
    print("Starting socket server")

    # Start the socket server on localhost and port 18999
    HOST, PORT = "0.0.0.0", 18999  # Set your server host and port
    sensor.start_socket_server(HOST, PORT)
    
    print("Starting main loop")
    
    while True:
         time.sleep(100)  # Use calculated delay  
        
if __name__ == "__main__":
    main()
