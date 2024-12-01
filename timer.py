import mouse, time, keyboard, shelve, dxcam
resultlist = [[False,True,True,True,True,True],[True,False,False,False,True,False],[True,True,False,True,True,True],[True,True,False,False,True,True],[False,False,True,True,True,True],[True,True,True,False,True,False],[True,True,True,True,True,False],[True,True,False,True,False,True],[True,True,True,True,True,True],[True,True,True,False,True,True]]
from tkinter import *
win=Tk()
win.geometry("185x150+1000+200")
win.overrideredirect(1)
win.attributes('-topmost', True)
speedframe = Frame(win,height=90,width=200)
timeframe = Frame(win,height=70,width=200)
speedframe.pack_propagate(False)
timeframe.pack_propagate(False)
speedframe.pack(pady=0)
timeframe.pack(pady=0)
speeddisplay = Label(speedframe, text=f'  BWO  ', font=('Freestyle Script',61,'bold'),foreground='#FFDC00',background='#3C0064')
timedisplay = Label(timeframe, text=f'  TIMER  ', font=('Bahnschrift Condensed',40,''),foreground='#FFDC00',background='#3C0064')
speeddisplay.pack(fill=BOTH,expand=True)
timedisplay.pack(fill=BOTH,expand=True)
win.update()



sheet = shelve.open('DoNotDelete')
setup = False
try:
    yoff = round(sheet['yoff'])
    xoff = round(sheet['xoff'])
    scale = sheet['scale']
    redbarstart = sheet['redbarstart']
    redbarstarty = sheet['redbarstarty']
except:
    setup = True
if setup:
    print('Please run the speedometer program in order to setup the speed reader before starting this program!')

ressetup = False
try:
    scrwidth = sheet['scrwidth']
    scrheight = sheet['scrheight']
    fps = sheet['fps']
except:
    ressetup = True

if ressetup:
    scrwidth = int(input('What is the width (in pixels) of your monitor?'))
    scrheight = int(input('What is the height (in pixels) of your monitor?'))
    fps = int(input('What is the fps you will be running A9 at?'))
    sheet['scrwidth'] = scrwidth
    sheet['scrheight'] = scrheight
    sheet['fps'] = fps

possetup = False
try:
    position = sheet['position']
except:
    possetup = True

locsetup = False
try:
    w = sheet['twinwidth']
    h = sheet['twinheight']
    x = sheet['twinx']
    y = sheet['twiny']
    win.geometry(f'{round(w)}x{round(h)}+{x}+{y}')
    win.update()
except:
    locsetup = True

if locsetup:
    print('\nWASD = move the speedometer, Left/Right = window size, press enter when done.\nNOTE: this speedometer should be positioned FULLY BELOW the red timer bar, and should not cover up the original speedometer.')
    x=1500
    y=200
    w = 185
    h = 150
    end = False
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
            w += 1.85
            h += 1.5
            time.sleep(.05)
            update = True
        if keyboard.is_pressed('Left'):
            w -= 1.85
            h -= 1.5
            time.sleep(.05)
            update = True
        if keyboard.is_pressed('Enter'):
            end = True
        if update:
            win.geometry(f'{round(w)}x{round(h)}+{x}+{y}')
            win.update()
        time.sleep(0.005)
    sheet['twinwidth'] = w
    sheet['twinheight'] = h
    sheet['twinx'] = x
    sheet['twiny'] = y

if possetup:
    print('please open a race and left click the center of the "%" symbol as accurately as possible, then return to this page.')
    end = False
    while end == False:
        if mouse.is_pressed():
            position = mouse.get_position()
            end = True
    sheet['position'] = position
x = round(position[0]-35*scale)
y = round(position[1]-18*scale)
sheet.close()


time.sleep(0.5)
camera = dxcam.create(output_color="RGB", max_buffer_len=1)
camera.start(region=(0,0,scrwidth-1,scrheight-1),target_fps=fps)

response = int(input('What do you want to do?\n1: Record a ghost\n2: Race against a ghost'))
if response == 1:
    while True:
        print('\nPress space to start recording. (Wait until you see the countdown)')
        timedisplay.config(text='  SPACE  ')
        win.update()
        keyboard.wait('Space')
        end = False
        start = None
        percent = 0
        timelist = []
        timedisplay.config(text='  RECORD  ')
        win.update()
        while start == None:
            t = time.time()
            image = camera.get_latest_frame()
            try:
                if (image[redbarstarty+2,redbarstart+2,0] >= 150 and image[redbarstarty+2,redbarstart+2,1] <= 20 and image[redbarstarty+2,redbarstart+2,2] <= 20):
                    start = t-0.5
            except TypeError:
                pass
        last = [False]*(round(36*scale))
        current = [None]*(round(36*scale))
        while end == False:
            t = time.time()-start
            image = camera.get_latest_frame()
            changes = 0
            try:
                for i in range(round(36*scale)):
                    if image[y+i,x,0] >= 150 and image[y+i,x,1] >= 150 and image[y+i,x,2] >= 150:
                        current[i] = True
                    else:
                        current[i] = False
                    if current[i] != last[i]:
                        changes += 1
                if changes > 0:
                    print('changes:',changes)
                if changes > 4:
                    last = current.copy()
                    output = [None,None,None]
                    error = False
                    for i in range(3):
                        result = []
                        xoff2 = round(xoff)
                        if image[round(44*scale)+yoff,round(48*scale)+xoff2,0] >= 230 and image[round(44*scale)+yoff,round(48*scale)+xoff2,1] >= 230 and image[round(44*scale)+yoff,round(48*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(78*scale)+yoff,round(16*scale)+xoff2,0] >= 230 and image[round(78*scale)+yoff,round(16*scale)+xoff2,1] >= 230 and image[round(78*scale)+yoff,round(16*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(42*scale)+yoff,round(24*scale)+xoff2,0] >= 230 and image[round(42*scale)+yoff,round(24*scale)+xoff2,1] >= 230 and image[round(42*scale)+yoff,round(24*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(64*scale)+yoff,round(24*scale)+xoff2,0] >= 230 and image[round(64*scale)+yoff,round(24*scale)+xoff2,1] >= 230 and image[round(64*scale)+yoff,round(24*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(78*scale)+yoff,round(43*scale)+xoff2,0] >= 230 and image[round(78*scale)+yoff,round(43*scale)+xoff2,1] >= 230 and image[round(78*scale)+yoff,round(43*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(25*scale)+yoff,round(71*scale)+xoff2,0] >= 230 and image[round(25*scale)+yoff,round(71*scale)+xoff2,1] >= 230 and image[round(25*scale)+yoff,round(71*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        try:
                            output[i] = resultlist.index(result)
                        except ValueError:
                            pass
                        xoff += 80*scale
                    xoff -= 240*scale
                    xoff = round(xoff)
                    if output[0] == None and output[1] != None and output[2] != None:
                        if output[1] > 0:
                            speed = int(f'{output[1]}{output[2]}')
                        elif output[1] == 0:
                            error = True
                    elif output[0] != None and output[1] != None and output[2] != None:
                        if output[0] <= 6:
                            speed = int(f'{output[0]}{output[1]}{output[2]}')
                        else:
                            error = True
                    else:
                        error = True
                    if error:
                        speed = None
                    timelist.append([t,speed])
                    speeddisplay.config(text=f'   {percent}   ',font=('Franklin Gothic Heavy',61,'bold'))
                    win.update()
                    print(f'{percent}% - {changes} pixels changed')
                    percent += 1
                    if not (image[redbarstarty+2,redbarstart+2,0] >= 150 and image[redbarstarty+2,redbarstart+2,1] <= 20 and image[redbarstarty+2,redbarstart+2,2] <= 20):
                        end = True
            except TypeError:
                pass
        response = input('\nDo you want to save this ghost? type yes or no')
        print(response)
        speeddisplay.config(text='  BWO  ',font=('Freestyle Script',61,'bold'))
        timedisplay.config(text='  SAVE?  ')
        if response.__contains__('yes'):
            timedisplay.config(text='  NAME?  ')
            name = input('\nWhat do you want to name this ghost?')
            sheet = shelve.open(name)
            percent = 0
            for i in timelist:
                sheet[f'{percent}-t'] = i[0]
                sheet[f'{percent}-s'] = i[1]
                percent += 1
            sheet.close()
        response = input('\nDo you want to record another ghost? type yes or no')
        if response == 'no':
            camera.stop()
            break



if response == 2:
    file = input('What is the name of the ghost you want to race against? (DO NOT INCLUDE FILE EXTENSION)')
    attempts = 0
    while True:
        sheet = shelve.open(file)
        timedisplay.config(text='  START  ')
        win.withdraw()
        win.update()
        end = False
        start = None
        percent = 0
        timelist = []
        while start == None:
            t = time.time()
            image = camera.get_latest_frame()
            try:
                if (image[redbarstarty+2,redbarstart+2,0] >= 150 and image[redbarstarty+2,redbarstart+2,1] <= 20 and image[redbarstarty+2,redbarstart+2,2] <= 20):
                    start = t-0.5
            except TypeError:
                pass
        last = [False]*(round(36*scale))
        current = [None]*(round(36*scale))
        attempts += 1
        print(f'Attempt {attempts}')
        speeddisplay.config(fg='white',bg='#808080',text='   0   ',font=('Franklin Gothic Heavy',61,'bold'))
        timedisplay.config(fg='white',bg='#808080',text='   0.00   ',font=('Franklin Gothic Heavy',40,'bold'))
        win.deiconify()
        while end == False:
            clock = time.time()
            t = time.time()-start
            image = camera.get_latest_frame()
            try:
                changes = 0
                for i in range(round(36*scale)):
                    if image[y+i,x,0] >= 150 and image[y+i,x,1] >= 150 and image[y+i,x,2] >= 150:
                        current[i] = True
                    else:
                        current[i] = False
                    if current[i] != last[i]:
                        changes += 1
                if changes > 4:
                    last = current.copy()
                    output = [None,None,None]
                    error = False
                    for i in range(3):
                        result = []
                        xoff2 = round(xoff)
                        if image[round(44*scale)+yoff,round(48*scale)+xoff2,0] >= 230 and image[round(44*scale)+yoff,round(48*scale)+xoff2,1] >= 230 and image[round(44*scale)+yoff,round(48*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(78*scale)+yoff,round(16*scale)+xoff2,0] >= 230 and image[round(78*scale)+yoff,round(16*scale)+xoff2,1] >= 230 and image[round(78*scale)+yoff,round(16*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(42*scale)+yoff,round(24*scale)+xoff2,0] >= 230 and image[round(42*scale)+yoff,round(24*scale)+xoff2,1] >= 230 and image[round(42*scale)+yoff,round(24*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(64*scale)+yoff,round(24*scale)+xoff2,0] >= 230 and image[round(64*scale)+yoff,round(24*scale)+xoff2,1] >= 230 and image[round(64*scale)+yoff,round(24*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(78*scale)+yoff,round(43*scale)+xoff2,0] >= 230 and image[round(78*scale)+yoff,round(43*scale)+xoff2,1] >= 230 and image[round(78*scale)+yoff,round(43*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        if image[round(25*scale)+yoff,round(71*scale)+xoff2,0] >= 230 and image[round(25*scale)+yoff,round(71*scale)+xoff2,1] >= 230 and image[round(25*scale)+yoff,round(71*scale)+xoff2,2] >= 230:
                            result.append(True)
                        else:
                            result.append(False)
                        try:
                            output[i] = resultlist.index(result)
                        except ValueError:
                            pass
                        xoff += 80*scale
                    xoff -= 240*scale
                    xoff = round(xoff)
                    if output[0] == None and output[1] != None and output[2] != None:
                        if output[1] > 0:
                            speed = int(f'{output[1]}{output[2]}')
                        elif output[1] == 0:
                            error = True
                    elif output[0] != None and output[1] != None and output[2] != None:
                        if output[0] <= 6:
                            speed = int(f'{output[0]}{output[1]}{output[2]}')
                        else:
                            error = True
                    else:
                        error = True
                    if error:
                        speed = 0
                    timelist.append([t,speed])
                    try:
                        timedelta = round(t-sheet[f'{percent}-t'],2)
                        speeddelta = speed-sheet[f'{percent}-s']
                    except:
                        timedelta = 0
                        speeddelta = 0
                    if timedelta > 0:
                        timedisplay.config(bg='#C00000',text=f'   +{abs(timedelta):.2f}   ')
                    elif timedelta < 0:
                        timedisplay.config(bg='#0000C0',text=f'   −{abs(timedelta):.2f}   ')
                    elif timedelta == 0:
                        timedisplay.config(bg='#808080',text=f'   ={abs(timedelta):.2f}   ')
                    if speeddelta > 0:
                        speeddisplay.config(bg='#00A000')
                    elif speeddelta < 0:
                        speeddisplay.config(bg='#E07000')
                    elif speeddelta == 0:
                        speeddisplay.config(bg='#808080')
                    speeddisplay.config(text=f'   {abs(speeddelta)}   ')
                    win.attributes('-topmost', True)
                    win.update()
                    percent += 1
                    if not (image[redbarstarty+2,redbarstart+2,0] >= 150 and image[redbarstarty+2,redbarstart+2,1] <= 20 and image[redbarstarty+2,redbarstart+2,2] <= 20):
                        end = True
            except TypeError:
                pass
        sheet.close()
        if percent >= 95:
            timedisplay.config(fg='#FFDC00',bg='#3C0064',text='  SAVE?  ',font=('Bahnschrift Condensed',40,''))
            speeddisplay.config(fg='#FFDC00',bg='#3C0064',text=' BWO ',font=('Freestyle Script',61,'bold'))
            win.update()
            end = False
            while end == False:
                if keyboard.is_pressed('Enter'):
                    response = 'yes'
                    end = True
                if keyboard.is_pressed('Backspace'):
                    response = 'no'
                    end = True
        else:
            response = 'no'
        if response == 'yes':
            timedisplay.config(text='  name  ')
            name = input('\nWhat do you want to name this ghost?')
            sheet = shelve.open(name)
            percent = 0
            for i in timelist:
                sheet[f'{percent}-t'] = i[0]
                sheet[f'{percent}-s'] = i[1]
                percent += 1
            sheet.close()