# Your AI for CTF must inherit from the base Commander class.  See how this is
# implemented by looking at the commander.py in the ./api/ folder.
from api import Commander

# The commander can send 'Commands' to individual bots.  These are listed and
# documented in commands.py from the ./api/ folder also.
from api import commands

# The maps for CTF are layed out along the X and Z axis in space, but can be
# effectively be considered 2D.
from api import Vector2
import random

class learningCommander(Commander):
    """
    Rename and modify this class to create your own commander and add mycmd.Placeholder
    to the execution command you use to run the competition.
    """

    def initialize(self, classifier = {'None': None}, randomRate = 0.0):
        """Use this function to setup your bot before the game starts."""
        self.verbose = True    # display the command descriptions next to the bot labels
        self.counter = 0
        self.randomRate = 0.0
        self.bots = {}
        for bot in self.game.team.members:
            self.bots[bot] = {'currentAction': None, 'storedRegressionVector' : None, 'forecastedValue' : None}
        # Classifier: Structured as {commands.Attack : (regression0, coefficient0), (regression1, coefficient1}... commands.Defend : (regression0.....)}
        self.actionClassifier = self.classifierGenerator()
        # Store all needed features.
        self.features = self.initialFeatureGenerator()
        
    # Regressions
    def attackRegression(self, bot, action): 
        distanceVector = self.features['enemyFlag'] - action[2]
        return 100/distanceVector.length()
    def currentActionRegression(self, bot, action): 
        return 5        
    def defendRegression(self, bot, action): 
        return 0        
    def chargeRegression(self, bot, action): 
        return 0        
    def moveRegression(self, bot, action): 
        return 0
    
    def initialFeatureGenerator(self):
        features = {}
        features['enemyFlag'] = self.game.enemyTeam.flag.position
        return features

    def featureUpdate(self):
        """Updates the features dictionary each tick."""
        pass
                 
    def classifierGenerator(self):
        classifier = {
        commands.Attack : [[self.attackRegression, 1]],
        'currentAction' : [[self.currentActionRegression, 2]],
        commands.Charge : [[self.chargeRegression, 1]],
        commands.Move : [[self.moveRegression, 2]],
        commands.Defend : [[self.defendRegression, 1]]
        }
        return classifier
        
    def tick(self):
        """Override this function for your own bots.  Here you can access all the information in self.game,
        which includes game information, and self.level which includes information about the level."""
        self.featureUpdate()
        self.counter += 1
        if self.counter%50 == 0:
            print '@@@@@@@@@@@@@@@@@@@@@@@@@ NEW TICK @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
            for bot in self.game.team.members:
                (action, value, regressionVector) = self.getAction(bot)
                self.issueAndStore(action, value, regressionVector)
                print 'BOT:  ', bot, 'Dictionary:  ', self.bots[bot], '\n'
 
    def getAction(self, bot):
        """
          Implements picking an action for a bot, allows for epsilon greedy exploration to be coded in.
          Returns value for issueAndStore to store for use in update function.
        """
        #Pick action either by exploring a random available option at a predetermined rate, or choosing amongst the best available options.
        legalActions = self.getCandidateActions(bot)
        if len(legalActions) == 0:
            (action, value, regressionVector) = (None, None, None)
        elif random.random() < self.randomRate == True:
            (action, value, regressionVector) = (random.choice(legalActions), None, None)
        else:
            (action, value, regressionVector)  = self.getPolicy(bot)
        return (action, value, regressionVector)

    def getPolicy(self, bot):
        """
          Compute the best action to take for a given bot by getting all values, choosing highest.
          Return action, valuation of action, regression vector used to get valuation.
        """
        candidateActions = self.getCandidateActions(bot)
        if len(candidateActions) == 0:
            print 'WARNING: EMPTY CANDIDATE ACTION LIST. FIX THAT FUNCTION!'
            return (None, None, None)
        bestAction = None
        bestValue = -100000000
        bestSet = []
        bestRegressionVector = None
        for action in candidateActions:
            (value, regressionVector) = self.getHueristicValue(bot, action)
            if value > bestValue:
                bestValue = value
                bestAction = action
                bestSet = []
                bestRegressionVector = regressionVector
            if value == bestValue:
                bestSet.append(action)          
        if len(bestSet) != 0:
            return (random.choice(bestSet), bestValue, bestRegressionVector)
        return (bestAction, bestValue, bestRegressionVector)

    def getCandidateActions(self, state):
        """Use random distribution across map to find potential points, add current action, defend facing a random set of directions.
        Alongside projected action by doing nothing."""
        bot = state
        actions = []
        for x in range(15):
            position = self.level.findRandomFreePositionInBox(self.level.area)         
            #Add random attack positions.
            actions.append([commands.Attack, bot, position,"Attacking selected point."])
            #Add defend commands with random directions.
            direction = Vector2(random.random()*random.sample([-1,1],1)[0], random.random()*random.sample([-1,1],1)[0])
            actions.append([commands.Defend, bot, direction, "Defending facing random direction."])
            #Add random move commands.
            actions.append([commands.Move, bot, position, "Moving to selected point."])
            #Add random charge commands.
            actions.append([commands.Charge, bot, position, "Charging to selected point."])            
        #Add current action string as an option. Parsed to special action that continues to execute current command.
        actions.append(['currentAction'])
        return actions

    def getHueristicValue(self, bot, action):
        #Takes bot, action, uses self.classifier dict to return a valuation of the bot's action.
        command = action[0]
        value = 0
        regressionVector = self.actionClassifier[command]
        for functionAndWeightPair in regressionVector:
            value += functionAndWeightPair[0](bot, action) * functionAndWeightPair[1]
        return (value, regressionVector)
        
    def getRegressionVector(self, command):
        vector = self.actionClassifier[command]
        return vector
        
    def issueAndStore(self, action, value, regressionVector):
        """Takes a list that constitutes a stored action, decides what kind of action it is,
        issues that command, tells commander bot is doing that command. We do this rather than directly
        issue so that currentAction can be a candidateAction."""
        
        command = action[0]
        if command == 'currentAction':
            #Doing nothing continues current action. This is explicitly included for conceptual simplicity.
            return
        bot = action[1]
        if command == commands.Attack:
            self.issue(command, bot, action[2], description = action[3])
        elif command == commands.Defend:
            self.issue(command, bot, facingDirection = action[2], description=action[3])
        elif command == commands.Charge:
            self.issue(command, bot, description = action[2])
        elif command == commands.Move:
            self.issue(command, bot, description = action[2])            
        #Stores the action as the bots currently executing action. Also store the regressions dict that picked it and the value of that state. 
        self.bots[bot]['currentAction'] = action
        self.bots[bot]['forecastedValue'] = value
        self.bots[bot]['storedRegressionVector'] = regressionVector

    def shutdown(self):
        """Use this function to teardown your bot after the game is over, or perform an
        analysis of the data accumulated during the game."""

        pass
