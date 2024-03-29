import c4d
import re
import os
from datetime import datetime

camera_ids = [1057516, 5103, 5103]

# sorting
def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [atoi(c) for c in re.split(r'(\d+)', text)]

class cameraToTake():
    def __init__(self, doc):
        
        self.doc = doc
        
        self.fps = doc.GetFps()

        if c4d.gui.QuestionDialog('Convert all cameras in the scene?\nClicking "No" will convert any selected cameras'):
            first_object = doc.GetFirstObject()
            objects = IterateHierarchy(first_object)
            objects.append(first_object)

        else:
            objects = doc.GetActiveObjects(True)

        self.cameras = self.filterCameras(objects)

        if not self.cameras:
            c4d.gui.MessageDialog('ERROR: No valid cameras found!')
            return
        
        self.buildCameraDataList()
        
        self.doc.StartUndo()

        if self.getAllRenderData() or self.getAllTakeData():
            if c4d.gui.QuestionDialog('Delete All Takes and Render Settings?'):
                self.deleteAllRenderData()
                self.deleteAllTakes()

        self.createRenderData()
        self.createTakeData()
        
        self.doc.EndUndo()

        self.writeLogInformation()

        c4d.gui.MessageDialog(self.prettyStats())

    def buildCameraDataList(self):
        self.camera_data_list = []

        for camera in self.cameras:
            data = {'Camera': camera}
            data['Frame Range'] = self.frameRangeFromCamera(camera)
            data['Take Name'] = camera.GetName()

            self.camera_data_list.append(data)

    def resetMinMax(self):
        self.min = c4d.BaseTime(0)
        self.max = c4d.BaseTime(0)
        self.count = 0

    def frameRangeFromCamera(self, camera):
        objects = getParents(camera)
        objects += [camera]

        self.resetMinMax()

        for object in objects:
            self.frameRangeFromObject(object)
            self.frameRangeFromTags(object)

        return self.min, self.max
    
    def updateMinMax(self, min, max):
        if min < self.min or self.count == 0:
            self.min = min

        if max > self.max or self.count == 0:
            self.max = max

        self.count += 1

    def frameRangeFromObject(self, object):
        track_ids = [
            c4d.ID_BASEOBJECT_REL_POSITION,
            c4d.ID_BASEOBJECT_REL_ROTATION,
            c4d.ID_BASEOBJECT_REL_SCALE
        ]

        return self.iterateTrackIDs(object, track_ids)
        
    def frameRangeFromTags(self, object):
        align_to_spline = object.GetTag(5699)
        target = object.GetTag(5676)

        if align_to_spline:
            track_ids = [c4d.ALIGNTOSPLINETAG_POSITION, c4d.ALIGNTOSPLINETAG_SEGMENT]

            self.iterateTrackIDs(align_to_spline, track_ids)

        if target:
            target_object = target[c4d.TARGETEXPRESSIONTAG_LINK]
            up_vector = target[c4d.TARGETEXPRESSIONTAG_UP_LINK]

            if target_object:
                self.frameRangeFromObject(target_object)

            if up_vector:
                self.frameRangeFromObject(up_vector)


    def iterateTrackIDs(self, object, track_ids):
        for track_id in track_ids:
            self.getTrackRange(object, track_id)
        
    def getTrackRange(self, object, track_id):
        camera_track_id = c4d.DescID(c4d.DescLevel(track_id))
        camera_track = object.FindCTrack(camera_track_id)

        if not camera_track:
            return None

        camera_curve = camera_track.GetCurve()

        keyframe_count = camera_curve.GetKeyCount()

        min = camera_curve.GetKey(0).GetTime()

        max = camera_curve.GetKey(keyframe_count-1).GetTime()

        self.updateMinMax(min, max)

        return min, max

    def filterCameras(self, objects):
        cameras = []

        for object in objects:
            if object.GetType() in camera_ids:
                cameras.append(object)

        cameras = sorted(
            cameras, key=lambda n: natural_keys(n.GetName()))

        return cameras

    def prettyStats(self):
        n_takes = len(self.camera_data_list)

        if n_takes == 1:
            take_plural = ''
        else:
            take_plural = 's'

        stats = 'Successfully Generated {} Take{}'.format(
            n_takes,
            take_plural
        )

        return stats

    def getAllRenderData(self):
        rd = self.doc.GetFirstRenderData()
        rd = rd.GetNext()
        rds = []
        
        while rd:
            rds.append(rd)
            rd = rd.GetNext()

        return rds
        
    def deleteAllRenderData(self):
        rds = self.getAllRenderData()
            
        for rd in rds:
            rd.Remove()

        c4d.EventAdd()
    
    def getAllTakeData(self):
        src_take_data = self.doc.GetTakeData()
        main_take = src_take_data.GetMainTake()
        td = main_take.GetDown()

        tds = []
        
        while td:
            tds.append(td)
            td = td.GetNext()

        return tds

    def deleteAllTakes(self):
        tds = self.getAllTakeData()
            
        for td in tds:
            td.Remove()
                
        c4d.EventAdd()
        
    def createRenderData(self):
        src_render_data = self.doc.GetFirstRenderData()
        
        for data_dict in self.camera_data_list:
            render_data: c4d.documents.RenderData = src_render_data.GetClone(c4d.COPYFLAGS_0)
            self.doc.InsertRenderDataLast(render_data)
            
            tstart, tend = data_dict['Frame Range']
            
            render_data.SetName(data_dict['Take Name'])
            render_data[c4d.RDATA_FRAMESEQUENCE] = 0
            render_data[c4d.RDATA_FRAMEFROM] = tstart
            render_data[c4d.RDATA_FRAMETO] = tend
            
            data_dict['Render Data'] = render_data

        c4d.EventAdd()
    
    def writeLogInformation(self):
        doc_simple = os.path.splitext(self.doc.GetDocumentName())[0]
        log_folder = os.path.expanduser('~/Documents/Camera to Take/Logs/'+doc_simple)
        current_datetime = datetime.now()
        
        log_filename = current_datetime.strftime("%m-%d-%Y_%H-%M-%S")
        log_filename = 'split-log_{}.txt'.format(log_filename)
        # log_filename = 'qwer.txt'
        log_file = os.path.join(log_folder, log_filename).replace('/', '\\')

        if not os.path.isdir(log_folder):
            os.makedirs(log_folder)

        log_info = []
        doc_path = os.path.join(
            self.doc.GetDocumentPath(), 
            self.doc.GetDocumentName()
        )

        doc_path = doc_path.replace('/', '\\')

        log_info.append('Scene File: '+doc_path)
        
        tab = '    '

        for data in self.camera_data_list:
            tstart, tend = data['Frame Range']
            fstart = tstart.GetFrame(self.fps)
            fend = tend.GetFrame(self.fps)

            log_info.append('')
            log_info.append('{}: {} - {}'.format(
                data['Take Name'], fstart, fend))
            
        with open(log_file, 'w') as f:
            f.write('\n'.join(log_info))

    def createTakeData(self):
        src_take_data = self.doc.GetTakeData()
        main_take = src_take_data.GetMainTake()
        child_take = main_take.GetDown()
        
        for data_dict in reversed(self.camera_data_list):
            take_data = src_take_data.AddTake(
                '', main_take, child_take)
            
            take_data.SetName(data_dict['Take Name'])
            take_data.SetCamera(src_take_data, data_dict['Camera'])
            take_data.SetRenderData(src_take_data, data_dict['Render Data'])
            
            data_dict['Take Data'] = take_data

        c4d.EventAdd()

def IterateHierarchy(op, children_only=False):
    '''
    hierarchy iteration
    https://developers.maxon.net/?p=596
    '''
    def GetNextObject(op):
        if op==None:
            return None
    
        if op.GetDown():
            return op.GetDown()
    
        while not op.GetNext() and op.GetUp():
            op = op.GetUp()

        if children_only and op == src:
            return None
        
        return op.GetNext()
    
    if op is None:
        return
 
    children = []

    src = op

    while op:
        children.append(op)
        op = GetNextObject(op)
 
    return children

def getParents(object):
    parents = []

    parent = object.GetUp()

    while parent:
        parents.append(parent)
        parent = parent.GetUp()

    return parents

class CommandData(c4d.plugins.CommandData):
    def Execute(self, doc):
        cameraToTake(doc)
        return True

def main():
    # iconMTX = c4d.bitmaps.BaseBitmap()
    # iconMTX.InitWith(os.path.join(os.path.dirname(__file__), "res", "stageSplitter.png"))
    iconMTX = None
    # Register Plugin
    try:
        c4d.plugins.RegisterCommandPlugin(
            1062995, 
            'Camera to Take', 
            0, 
            iconMTX,
            'Turns cameras into takes', 
            CommandData()
        )
    except:
        cameraToTake(
            c4d.documents.GetActiveDocument())

if __name__ == '__main__':
    main()