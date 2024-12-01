import pyscreeze, time, keyboard
from PIL import Image
resultlist = [[False,True,True,True,True,True],[True,False,False,False,True,False],[True,True,False,True,True,True],[True,True,False,False,True,True],[False,False,True,True,True,True],[True,True,True,False,True,False],[True,True,True,True,True,False],[True,True,False,True,False,True],[True,True,True,True,True,True],[True,True,True,False,True,True]]
import shelve
sheet = shelve.open('DoNotDelete')
setup = False
try:
    yoff = sheet['yoff']
    xoff = sheet['xoff']
    scale = sheet['scale']
except:
    setup = True
setup = True
sheet.close()
if setup:
    print('''\n
          Setup is required the first time you use this program!
          Open a race in the game and make sure you are playing with the screen in the same position you would normally use.
          Once the in-game speedometer reaches more than 100 km/h, press Enter and wait for 30 seconds.
          Then, come back to this page and follow the instructions on positioning the speedometer.''')
    keyboard.wait('Enter')
    found = False
    image = pyscreeze.screenshot()
    for g in range(round((image.width)/4)):
        x = g+round((image.width)*(3/4))
        stop = False
        y = 0
        erase = False
        while not stop:
            color = image.getpixel((x,y))
            if (color[0] >= 150 and color[1] <= 10 and color[2] <= 20):
                if not found:
                    redbarstart = x
                    redbarstarty = y
                    found = True
                stop = True
            if y > (image.height)/4:
                stop = True
                erase = True
            y += 1
        if not erase:
            redbarend = x
    try:
        redbar = round((redbarend-redbarstart)*1.0175)
    except:
        print('\n          ERROR: could not find speedometer, please wait to press enter until you are in a race and travelling faster than 100 km/h! (restart the program and try again)')
        keyboard.wait('~')
    scale = redbar/385
    resultlist = [[False,True,True,True,True,True],[True,False,False,False,True,False],[True,True,False,True,True,True],[True,True,False,False,True,True],[False,False,True,True,True,True],[True,True,True,False,True,False],[True,True,True,True,True,False],[True,True,False,True,False,True],[True,True,True,True,True,True],[True,True,True,False,True,True]]
    error = False
    yoff = image.height/20
    xoff = redbarstart
    sheet = shelve.open('DoNotDelete')
    sheet['redbarstart'] = redbarstart
    sheet['redbarstarty'] = redbarstarty
    end = False
    start = time.time()
    while end == False:
        image = pyscreeze.screenshot()
        error = True
        if time.time() - start >= 30:
            end = True
            error = False
            print('DONE!')
        while error:  
            error = False
            output = [None,None,None]
            for i in range(3):
                result = []
                if image.getpixel((round(48*scale)+xoff,round(44*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                if image.getpixel((round(16*scale)+xoff,round(78*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                if image.getpixel((round(24*scale)+xoff,round(42*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                if image.getpixel((round(24*scale)+xoff,round(64*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                if image.getpixel((round(43*scale)+xoff,round(78*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                if image.getpixel((round(71*scale)+xoff,round(25*scale)+yoff)) >= (230,230,230):
                    result.append(True)
                else:
                    result.append(False)
                try:
                    output[i] = resultlist.index(result)
                except ValueError:
                    pass
                xoff += 80*scale
            if output[0] != None and output[1] != None and output[2] != None:
                if output[0] <= 6:
                    print(f'{output[0]}{output[1]}{output[2]}',round(xoff-240*scale),yoff)
                else:
                    error = True
            else:
                error = True
            if error:
                if xoff < image.width:
                    xoff += 1
                else:
                    yoff += 1
                    xoff = round(redbarstart+240*scale)
                if yoff >= image.height/8:
                    end = True
                    error = False
                    print('\n          ERROR: could not find speedometer, please wait to press enter until you are in a race! (restart the program and try again)')
            xoff -= 240*scale
sheet = shelve.open('DoNotDelete')
sheet['yoff'] = yoff
sheet['xoff'] = xoff
sheet['scale'] = scale
count = 0
from tkinter import *
win=Tk()
win.geometry("220x100+1500+200")
win.overrideredirect(1)
win.attributes('-topmost', True)
display = Label(win, text=f'000', font=('Aerial 80'),foreground='white',background='black')
display.pack(pady=0, anchor =CENTER)
win.update()
end = False
locsetup = False
try:
    w = sheet['winwidth']
    h = sheet['winheight']
    x = sheet['winx']
    y = sheet['winy']
    t = sheet['textsize']
except:
    locsetup = True
if locsetup:
    print('\nWASD = move the speedometer, Up/Down = font size, Left/Right = window size, press enter when done.\nNOTE: this speedometer should be positioned FULLY BELOW the red timer bar, and should not cover up the original speedometer.')
    x=1500
    y=200
    w = 220
    h = 100
    t = 80
    while end == False:
        update = False
        if keyboard.is_pressed('W'):
            y -= 1
            update = True
        if keyboard.is_pressed('S'):
            y += 1
            update = True
        if keyboard.is_pressed('A'):
            x -= 1
            update = True
        if keyboard.is_pressed('D'):
            x += 1
            update = True
        if keyboard.is_pressed('Right'):
            w += 2.2
            h += 1
            time.sleep(.05)
            update = True
        if keyboard.is_pressed('Left'):
            w -= 2.2
            h -= 1
            time.sleep(.05)
            update = True
        if keyboard.is_pressed('Up'):
            t += 1
            time.sleep(.1)
            update = True
        if keyboard.is_pressed('Down'):
            t -= 1
            time.sleep(.1)
            update = True
        if keyboard.is_pressed('Enter'):
            end = True
        if update:
            win.geometry(f'{round(w)}x{h}+{x}+{y}')
            display.config(font=f'Aerial {t}')
            win.update()
        time.sleep(0.005)
    sheet['winwidth'] = w
    sheet['winheight'] = h
    sheet['winx'] = x
    sheet['winy'] = y
    sheet['textsize'] = t
    print(f'Window Width: {w}')
    print(f'Window Height: {h}')
    print(f'Window X Position: {x}')
    print(f'Window Y Position: {y}')
    print(f'Text Size: {t}')
sheet.close()
print("Sheet closed")
while True:
    image = pyscreeze.screenshot()
    output = [None,None,None]
    error = False
    for i in range(3):
        result = []
        if image.getpixel((round(48*scale)+xoff,round(44*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        if image.getpixel((round(16*scale)+xoff,round(78*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        if image.getpixel((round(24*scale)+xoff,round(42*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        if image.getpixel((round(24*scale)+xoff,round(64*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        if image.getpixel((round(43*scale)+xoff,round(78*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        if image.getpixel((round(71*scale)+xoff,round(25*scale)+yoff)) >= (230,230,230):
            result.append(True)
        else:
            result.append(False)
        try:
            output[i] = resultlist.index(result)
        except ValueError:
            pass
        xoff += 80*scale
    if output[0] == None and output[1] != None and output[2] != None:
        if output[1] > 0:
            display.config(text=f' {output[1]}{output[2]}')
        elif output[1] == 0:
            error = True
    elif output[0] != None and output[1] != None and output[2] != None:
        if output[0] <= 6:
            outputnum = int(f'{output[0]}{output[1]}{output[2]}')
            if 100 <= outputnum < 235:
                result = (outputnum+35)/1.35
            elif 235 <= outputnum < 420:
                result = (outputnum + 135)/1.85
            elif 420 <= outputnum < 550:
                result = (outputnum + 360)/2.6
            elif 550 <= outputnum <= 600:
                result = outputnum - 200
            else:
                result = 0
                error = True
            display.config(text=f'{round(result)}')
        else:
            error = True
    else:
        error = True
    if error:
        display.config(text=f'ER!')
    xoff -= 240*scale
    win.update()