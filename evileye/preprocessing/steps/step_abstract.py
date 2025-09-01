from abc import abstractmethod

class StepAbstarct():
    def __init__(self, aNextStep=None):
        self.nextStep = aNextStep
    
    def applySequence(self, aFrame):
        if aFrame.all() == None:
            raise Exception(f"Empty frame passed to preprocessing step")
        
        frameAfterStep = self._applyStep(aFrame)
        if self.nextStep == None:
            return frameAfterStep
        return self._applyNextStep(frameAfterStep)
            
    def _applyNextStep(self, aFrameAfterStep):
        return self.nextStep.applySequence(aFrameAfterStep)
    
    
    @abstractmethod
    def _applyStep(self, aFrame):
        pass

    