#!/usr/bin/env python
import sys
import time
import os
import csv
sys.path.append('/home/testbench2/root_6_08/lib')
import ROOT
ROOT.gROOT.LoadMacro("rootMacros/MakePedestalTTree.cxx")
ROOT.gROOT.LoadMacro("rootMacros/PlotAllWaveforms.cxx")
ROOT.gROOT.LoadMacro("rootMacros/PlotSomeWaveforms.cxx")
ROOT.gROOT.LoadMacro("rootMacros/MakePedSubtractedTTree.cxx")
ROOT.gROOT.LoadMacro("rootMacros/PlotMultiChanPulseHeightDist.cxx")
ROOT.gROOT.LoadMacro("rootMacros/PlotPulseHeightDist.cxx")
ROOT.gROOT.LoadMacro("rootMacros/PlotTriggeredEvents.cxx")
SCRIPTPATH = os.path.dirname(__file__)
sys.path.append( SCRIPTPATH+'/lib/' )
import linkEth

#ALL WINDOWS: sudo ./doEverything.py eth4 KLMS0173 75p18 128 0 0 0 3 3 0 0
#SELF TRIGGERING: sudo ./doEverything.py eth4 KLMS0173 75p18 10 1 -1 18 3 3 0 0
#---------------- USAGE ----------------#
usageMSG="MultiASIC take data record usage:\n"+\
"./doEverything.py "+\
    "<Interface> "+\
    "<S/N> "+\
    "<HV> "+\
    "<NumEvts> "+\
    "<TrigType> "+\
    "<WinStart> "+\
    "<WinOffset> "+\
    "<ASIC> "+\
    "<OpMode> "+\
    "<OutMode> "+\
    "<TrgThresh>\n"+\
"Where:\n"+\
    "<Interface> = (e.g.) eth4\n"+\
    "<S/N> = KLMS_0XXX\n"+\
    "<HV> = (e.g.) 74p9\n"+\
    "<NumEvts> > 0\n"+\
    "<TrigType>:\n"+\
        "\t0 = Software\n"+\
        "\t1 = Hardware\n"+\
    "<WinStart> = integer in range [0, 508]\n"+\
        "\tor -1 to disable fixed-window reading\n"+\
    "<WinOffset> = integer in range [0, 508]\n"+\
    "<ASIC> = integer in range [0, 9]\n"+\
    "<OpMode>: \n"+\
        "\t1 = Pedestal subtracted data\n"+\
        "\t2 = Pedestals only\n"+\
        "\t3 = Raw Waveform only\n"+\
    "<OutMode>:\n"+\
        "\t 0 = Waveforms\n"+\
        "\t 1 = Charge & Time\n"+\
        "\t-1 = Don't touch this register\n"+\
    "<TrigThresh> = (e.g.) 40"

RecordPedData = False
if (len(sys.argv)!=12):
    if (len(sys.argv)==13 and sys.argv[12]=='-peds'):
        RecordPedData = True
    else:
        print usageMSG
        exit(-1)

interface   = str(sys.argv[1])
SN          = str(sys.argv[2])
rawHV       = str(sys.argv[3])
numEvts     = int(sys.argv[4])
trgTyp      = int(sys.argv[5])
winStart    = int(sys.argv[6])
winOffset   = int(sys.argv[7])
asicNo      = int(sys.argv[8])
opMode      = int(sys.argv[9])
outMode     = int(sys.argv[10])
usrOffset   = int(sys.argv[11])

if numEvts<0 or trgTyp<0 or trgTyp>1 or winStart<-1 or winStart>508 or winOffset<0 or winOffset>508 or asicNo<0 or asicNo>9 or opMode<1 or opMode>3:
    print usageMSG
    exit(-1)

fxdWin=1
if winStart==-1: #prevents setting SCROD register "use_fixed_dig_start_win"
    fxdWin=0



#--------- ETHERNET CONFIGURATION ----------#
addr_fpga = '192.168.20.5'
addr_pc = '192.168.20.1'
port_pc = '28672'
port_fpga = '24576'
syncwd="000000010253594e4300000000" # must be send before every command string
# Make UDP class for receiving/sending UDP Packets


#--- CONFIGURE SCROD(?) & SET TRIG. THRESHOLD AND HV TO NULL ---#
cmdZeroTh = cmdHVoff = syncwd
for Ich in range (0,16):
    cmdHVoff  += hex( int('C',16)*(2**28) | asicNo*(2**20) | (Ich)*(2**16) | 255 ).split('x')[1]
    cmdZeroTh += hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*Ich)*(2**16) | 0 ).split('x')[1]+"AE000100"

#---- LOOK FOR CALIBRATION VALUES FROM TODAY ----#
calib_file_name = "calib/"+SN+"_HV"+rawHV+"_"+"ASIC"+str(asicNo)+".txt"
if not (os.path.isfile(calib_file_name)):  #infile.mode == 'r':
    os.system("sudo ./setThresholdsAndGains.py "+interface+" "+SN+" "+rawHV+" "+str(asicNo))
num_lines = int(os.popen("sed -n '$=' "+calib_file_name).read())
#print "file: %s, num lines: %d" % (calib_file_name, num_lines)
if (num_lines == 15):
    infile = open(calib_file_name, 'r')
else:
    print "Calibration file has wrong number of lines. Exiting!"
    print "Remove faulty calibration file and rerun script."
    quit()
csvFile = csv.reader(infile, delimiter='\t')
fileLines= []
for line in csvFile:
    fileLines.append(line)
infile.close()
thBase = [int(line[0]) for line in fileLines]
hvBest = [int(line[1]) for line in fileLines]
print "\nFound threshold base from file:\n%s" % thBase
print "\nFound HV values from file:\n%s\n" % hvBest


testCh = 0
for trial in range(4):
    usrOffset = 250 + 50*trial
    numEvts = 35000 - 10000*trial
    #------------------------------------------------------------------------------#
    #-------------------SETUP ASIC AND SCROD FOR DATA COLLECTION-------------------#
    #------------------------------------------------------------------------------#
    #----SET THRESHOLD OFFSET TO USER SPECIFIED VALUE----#
    cmdASIC_Th = cmdASIC_HV = syncwd
    for chNo in range(15):
        if (chNo == testCh):
            cmdASIC_Th += hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*chNo)*(2**16) | (thBase[chNo] - usrOffset) ).split('x')[1]#+"AE000100"
            cmdASIC_HV += hex( int('C',16)*(2**28) | asicNo*(2**20) | (chNo)*(2**16)   | hvBest[chNo] ).split('x')[1]#+"AE000100"
        else:
            cmdASIC_Th += hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*chNo)*(2**16) | (thBase[chNo] -2000 )).split('x')[1]#+"AE000100"
            cmdASIC_HV += hex( int('C',16)*(2**28) | asicNo*(2**20) | (chNo)*(2**16)   | 255 ).split('x')[1]#+"AE000100"
    ctrl = linkEth.UDP(addr_fpga, port_fpga, addr_pc, port_pc, interface)
    ctrl.open()
    #ctrl.KLMprint(cmdASIC_Th, "cmdASIC_Th")
    #ctrl.KLMprint(cmdASIC_HV, "cmdASIC_HV")
    time.sleep(0.05)
    ctrl.send(cmdHVoff)
    time.sleep(0.1)
    ctrl.send(cmdASIC_Th)
    time.sleep(0.1)
    ctrl.send(cmdASIC_HV)
    time.sleep(0.1)

    #----DATA-COLLECTION PARAMETERS FOR SCROD REGISTERS----#
    cmd_runConfig = syncwd + "AF250000" + "AE000100"#disable ext. trig
    cmd_runConfig += hex(int('AF3E0000',16) | fxdWin*(2**15) | fxdWin*winStart ).split('x')[1] +"AE000100"#set win start---> is set to zero for internal triggering
    cmd_runConfig += hex(int('AF360000',16) | 0              | winOffset       ).split('x')[1] +"AE000100"#set win offset
    cmd_runConfig += hex(int('AF330000',16) | 0              | 2**asicNo       ).split('x')[1] +"AE000100"#set asic number
    cmd_runConfig += hex(int('AF260000',16) | opMode*(2**12) | 2**7            ).split('x')[1] +"AE000100"#CMDREG_PedDemuxFifoOutputSelect(13 downto 12)-->either wavfifo or pedfifo,CMDREG_PedSubCalcMode(10 downto 7)-->currently only using bit 7: 1 for peaks 2 for troughs, sample offset is 3400 o6 600 respectively
    cmd_runConfig += hex(int('AF270000',16) | trgTyp*(2**15) | 2**asicNo       ).split('x')[1] +"AE000100"#set trig mode & asic trig enable
    cmd_runConfig += hex(int('AF4A0000',16) | outMode*(2**8) | 1*2**4 + 2*2**0 ).split('x')[1] +"AE000100"#set outmode and win boundaries for trigger bits: x12 scans 1 win back and two forward
    cmd_runConfig += "AF4F0002" # external trigger bit format

    trig_cmd = "AF00FFFF"+"AF00FFFF"+"AF370001"+"AE000001"+"AF370000"+"AE000001"+"AF320001"+"AE000001"+"AF320000" # modified original from AF00FFF+AF00FFFFF / CK
    cmd_FIFO_reset = "AF260000"+"AE000100"+"AF260800"+"AE000100"+"AF260000"+"AE000100"+"AF261080"

    cmd_pedConfig = syncwd + "AE001000"+"AF250000"+"AE000100"#disable ext. trig
    cmd_pedConfig += "AF360000"+"AE000100"#  set offset to zero
    cmd_pedConfig += hex(int('AF330000',16) | 2**asicNo).split('x')[1] +"AE000100"#set asic number
    cmd_pedConfig += "AF263000"+"AE000100"#pedsub mode: (13 downto 12)="11" is waveform only (no subtraction), bit (7)="0" is peak mode
    cmd_pedConfig += "AF4A0000"+"AE000100"+"AF4F0000"#set outmode to "waveforms" & trigBit search range to +/- 0 windows & ext. trig. bit format to zero.



    #------------------------------------------------------------------------------#
    #-------------------------------DATA COLLECTION--------------------------------#
    #------------------------------------------------------------------------------#
    print("Taking ASIC_"+str(asicNo)+" data . . .")
    buffSize = 20000
    os.system("echo -n > outdir/data.dat") #clean file without removing (prevents ownership change to root in this script)
    f = open('outdir/data.dat','ab') #a=append, b=binary
    t1 = time.time()
    if (RecordPedData):
        ctrl.send(cmdHVoff)
        time.sleep(0.1)
        ctrl.send(cmd_pedConfig)
        ctrl.KLMprint(cmd_pedConfig, "ped_Config")
        time.sleep(0.1)
        for i in range(0, 128):
            ctrl.send(syncwd+hex(int('AF3E0000',16) | 2**15 | i*4 ).split('x')[1]) #set win start
            time.sleep(0.1)
            ctrl.send(syncwd+trig_cmd)
            rcv = ctrl.receive(buffSize)# rcv is string of Hex
            time.sleep(0.001)
            if (i%80)==0: print
            sys.stdout.write('.')
            sys.stdout.flush()
            rcv = linkEth.hexToBin(rcv)
            f.write(rcv) # write received binary data into file (outdir/data.dat)
    else:
        if numEvts<=1200: printRate = 1
        else if numEvts>1200 and numEvts<=12000: printRate = 10
        else: printRate = 100
        print("each dot represents %d event(s)" % printRate)
        time.sleep(0.1)
        ctrl.send(cmd_runConfig)
        #ctrl.KLMprint(cmd_runConfig, "run_Config")
        time.sleep(0.1)
        for i in range(0, numEvts):
            if trgTyp==0:
                ctrl.send(syncwd+trig_cmd)
            rcv = ctrl.receive(buffSize)# rcv is string of Hex
            time.sleep(0.001)
            if i!=0 and (i%(80*printRate)==0:
                sys.stdout.write("<--%d\n" % i)
                sys.stdout.flush()
            if ((i%printRate)==0):
                sys.stdout.write('.')
                sys.stdout.flush()
            rcv = linkEth.hexToBin(rcv)
            f.write(rcv) # write received binary data into file
    t2 = time.time()

    f.close()
    ctrl.close()
    time.sleep(0.1)


    #------------------------------------------------------------------------------#
    #---------------------CALL ON PARSING AND PLOTTING SCRIPTS---------------------#
    #------------------------------------------------------------------------------#

    #---- SETUP FILES FOR READING/WRITING ----#
    uniqueID = SN + "_HV" + rawHV + "_" + time.strftime("%Y%m%d_%H%M%S",time.localtime())
    working_dir = "outdir/" + uniqueID
    os.system("mkdir " + working_dir + " && chmod g+w " + working_dir)
    os.system("chown -R testbench2:testbench2 " + working_dir)
    root_filename = working_dir + "/" + uniqueID + ".root"
    waveformOutfile = working_dir + "/waveformSamples.txt"
    trigBitOutfile = working_dir + "/triggerBits.txt"
    pedfile = "calib/" + SN + "_pedfile.root"
    #---- RUN DATA-PARSING EXECUTABLE ----#
    print("\nParsing ASIC_" + str(asicNo) + " data . . .\n")
    os.system("./bin/tx_ethparse1_ck outdir/data.dat " + waveformOutfile + " " + trigBitOutfile + " " + str(outMode))
    time.sleep(0.1)
    print "Data written in:   %s" % waveformOutfile

    #---- RUN ROOT MACROS ----#
    if (RecordPedData):
        print("Saving pedestal data to TTree")
        ROOT.MakePedestalTTree(waveformOutfile, pedfile)
        time.sleep(0.1)
        os.system("chown -R testbench2:testbench2 " + pedfile)
        #next two lines are for sanity check
        ROOT.MakePedSubtractedTTree(waveformOutfile, pedfile, root_filename)
        ROOT.PlotAllWaveforms(root_filename)
        print "Data written in:   %s" % pedfile
    else:
        print("Writing data into a TTree . . .\n")
        ROOT.MakePedSubtractedTTree(waveformOutfile, pedfile, root_filename)
        print "Data written in:   %s" % root_filename
        os.system("chmod a+w " + root_filename)
        os.system("chown -R testbench2:testbench2 " + root_filename)
        time.sleep(0.1)
        os.system("rm "+waveformOutfile)
        #ROOT.PlotSomeWaveforms(root_filename)
        out_file = "PHD_ASIC"+str(asicNo)+"_Ch"+str(testCh)+"_thresh"+str(usrOffset)+"_"+str(numEvts/1000)+"kEvts_HVtrim"+str(hvBest[testCh])
        ROOT.PlotPulseHeightDist(root_filename, out_file)
        #ROOT.PlotTriggeredEvents(root_filename)


    EvtRate = numEvts/float(t2-t1)
    print "Overall hit rate was %.2f Hz" % EvtRate
