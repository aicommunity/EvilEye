from .step_abstract import StepAbstarct

class Output(StepAbstarct):
    def __init__(self, aNextStep=None):
        if aNextStep != None:
            raise Exception(f"Final sequence step is not None (next step is {aNextStep.__class__.__name__})")
        super().__init__(aNextStep)
        
    def _applyStep(self, aFrame):
        return aFrame
        
          