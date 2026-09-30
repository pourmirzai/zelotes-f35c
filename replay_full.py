import os, glob, select, sys, time
dev = None
for hr in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
    uev = open(hr + '/device/uevent').read()
    if '0000320F:00002261' in uev and 'input1' in uev:
        dev = '/dev/' + os.path.basename(hr)
fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
def send(h, wait=0.3):
    os.write(fd, bytes.fromhex(h))
    end = time.time() + wait
    while time.time() < end:
        r,_,_ = select.select([fd],[],[],0.05)
        if r: os.read(fd,64)
send('04dc03' + '00'*13)
send(sys.argv[1])
send('04001a06' + '00'*27 + '02')
print('sent', sys.argv[1][:40])
