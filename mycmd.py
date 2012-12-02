#Justin's test
#Tim's test
# Your AI for CTF must inherit from the base Commander class.  See how this is
# implemented by looking at the commander.py in the ./api/ folder.
from api import Commander

# The commander can send 'Commands' to individual bots.  These are listed and
# documented in commands.py from the ./api/ folder also.
from api import commands

# The maps for CTF are layed out along the X and Z axis in space, but can be
# effectively be considered 2D.
from api import Vector2
import util, random

class learningCommander(Commander):
    """
    Rename and modify this class to create your own commander and add mycmd.Placeholder
    to the execution command you use to run the competition.
    """

    def initialize(self, modes = {'None':None}, randomChoiceRate = 0):
        """Use this function to setup your bot before the game starts."""
        self.verbose = True    # display the command descriptions next to the bot labels
        self.counter = 0
        self.values = util.Counter()
        self.randomRate = randomChoiceRate
        self.bots = {}
        for bot in self.game.team.members:
            self.bots[bot] = {'currentAction': None}
            
        #Contains the sets of features and feature weights for different situations.
        #The modeSelectFeatures and weights are used to score relevance for evaluating a bot's state, candidateAction pairs at a tick. 
        #Structured as modes = {}
        #    modes['modeX'] = {
        #       'features'           : {'commands.Defend' : [feat0, feat1... featn], 'commands.Attack' : [feat0,...]...},
        #       'weights'            : {'commands.Defend' : [feat0, feat1... featn], 'commands.Attack' : [feat0,...]...},
        #       'modeSelectFeatures' : {'commands.Defend' : [feat0, feat1... featn], 'commands.Attack' : [feat0,...]...},
        #       'modeSelectWeights'  : {'commands.Defend' : [feat0, feat1... featn], 'commands.Attack' : [feat0,...]...}
        #       }
        #TODO: Consider storing and extracting these dictionaries in and from a database?
        self.modes = modes

    def tick(self):
        """Override this function for your own bots.  Here you can access all the information in self.game,
        which includes game information, and self.level which includes information about the level."""
        self.counter += 1
        if self.counter%30 == 0:
            for bot in self.game.team.members:
                action = self.getAction(bot)
                self.issueAndStore(action)

    def getAction(self, state):
        """
          Implements picking an action at a given state, this is where exploration is coded in. 
        """
        # Pick action either by exploring at a predetermined random rate, or choosing amongst the best available options.
        legalActions = self.getCandidateActions(state)
        if len(legalActions) == 0:
          action = None
        elif util.flipCoin(self.randomRate) == True:
          action = random.choice(legalActions)
        else:
          action = self.getPolicy(state)
        return action

    def getPolicy(self, state):
        """
          Compute the best action to take in a state.  Note that if there
          are no legal actions, which is the case at the terminal state,
          you should return None.
        """
        legalActions = self.getCandidateActions(state)
        if len(legalActions) == 0:
          return None
        bestAction = None
        best = -100000000
        bestSet = []
        for action in legalActions:
          value = self.getHueristicValue(state,action)
          if value > best:
            best = value
            bestAction = action
            bestSet = []
          if value == best:
            bestSet.append(action)          
        if len(bestSet) != 0:
          return random.choice(bestSet)
        return bestAction

    
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
        #Takes bot, action, uses self.modes dict to return a valuation of the bot's action.
        mode = self.getMode(bot, action)
        command = action[0]
        value = 0
        if mode != None:
            for feature in self.modes[mode][str(command)]:
                value += feature(bot)
        if command == commands.Attack: 
            distanceVector = self.game.enemyTeam.flag.position - action[2]
            return value + 100/distanceVector.length()
        elif command == 'currentAction':
            return value + 10
        elif command == commands.Defend:
            return  value + 0
        elif command == commands.Charge:
            return value + 0
        elif command == commands.Move:
            return value + 0
        
    def getMode(self, state, action):
        #Pick the best feature weighting function mode given a current situation.
        bot = state
        for mode in self.modes.keys():
            pass
        return None
        
    def getFeatureVector(self, state, commandType, mode):
        bot = state
        featureVector = self.modes[mode][features][commandType]
        return featureVector
        
    
    def updateWeights(self, state, action, nextState, reward):
        """
           Should update your weights based on transition
        """
        
        features = self.getFeatures(state,action)
        features2 = features.copy()
        weights2 = self.weights.copy()
        for feature in features.keys():
          weights2[feature] = self.weights[feature] + self.alpha*features2[feature]*(reward + self.discount*self.getValue(nextState) - self.getQValue(state,action))
        self.weights = weights2
        self.features = features2
        
    def issueAndStore(self, action):
        """Takes a list that constitutes a stored action, decides what kind of action it is,
        issues that command, tells commander bot is doing that command. We do this rather than directly
        issue so that currentAction can be a candidateAction."""
        
        command = action[0]
        if command == 'currentAction':
            #Doing nothing continues current action. This is explicitly included for conceptual simplicity.
            return
        bot = action[1]
        if command == commands.Attack:
            print action
            self.issue(command, bot,action[2], description=action[3])
        elif command == commands.Defend:
            self.issue(command, bot, facingDirection = action[2], description=action[3])
        elif command == commands.Charge:
            self.issue(command, bot, description = action[2])
        elif command == commands.Move:
            self.issue(command, bot, description = action[2])            
        #Stores the action as the bots currently executing action. 
        self.bots[action[1]] = action
        
    def getQValue(self, state, action):
        """
          Returns Q(state,action)
          Should return 0.0 if we never seen
          a state or (state,action) tuple
        """
        value = 0
        features = self.getFeatures(state,action)
        for feature in features.keys():
          value += features[feature]*self.weights[feature]
        return value
                

    def shutdown(self):
        """Use this function to teardown your bot after the game is over, or perform an
        analysis of the data accumulated during the game."""

        pass


class defaultCommander(Commander):
    """
    Rename and modify this class to create your own commander and add mycmd.Placeholder
    to the execution command you use to run the competition.
    """

    def initialize(self, randomChoiceRate = 0):
        """Use this function to setup your bot before the game starts."""
        self.verbose = True    # display the command descriptions next to the bot labels
        self.counter = 0

    def tick(self):
        """Override this function for your own bots.  Here you can access all the information in self.game,
        which includes game information, and self.level which includes information about the level."""
        
        # for all bots which aren't currently doing anything
        for bot in self.game.bots_available:
            if bot.flag:
                # if a bot has the flag run to the scoring location
                flagScoreLocation = self.game.team.flagScoreLocation
                self.issue(commands.Charge, bot, flagScoreLocation, description = 'Run to my flag')
            else:
                # otherwise run to where the flag is
                enemyFlag = self.game.enemyTeam.flag.position
                self.issue(commands.Charge, bot, enemyFlag, description = 'Run to enemy flag')

    def shutdown(self):
        """Use this function to teardown your bot after the game is over, or perform an
        analysis of the data accumulated during the game."""

        pass
