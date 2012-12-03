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
    # Regressions
    def attackRegression(self, bot, action): 
        distanceVector = self.features['enemyFlag'] - action[2]
        return 100/(distanceVector.length()+3)
    def currentActionRegression(self, bot, action): 
        return 5        
    def defendRegression(self, bot, action): 
        return 0        
    def chargeRegression(self, bot, action): 
        return 0        
    def moveRegression(self, bot, action): 
        return 0   
    def botsInSightCone(self, bot, action):
        enemybotsseen = 0
        for bot in self.game.bots_alive:
               VisibleLiveEnemies = [enemybot for enemybot in bot.visibleEnemies if enemybot.health != 0]
               enemybotsseen += len(VisibleLiveEnemies)
        return enemybotsseen
        
    def initialFeatureGenerator(self):
        features = {}
        features['enemyFlag'] = self.game.enemyTeam.flag.position
        return features

    def featureUpdate(self):
        """Updates the features dictionary each tick."""
        pass
                 
    def classifierGenerator(self):
        classifier = {
        commands.Attack : [[self.attackRegression, 1], [self.botsInSightCone, 1]],
        'currentAction' : [[self.currentActionRegression, 1], [self.botsInSightCone, 1]],
        commands.Charge : [[self.chargeRegression, 1], [self.botsInSightCone, 1]],
        commands.Move : [[self.moveRegression, 1], [self.botsInSightCone, 1]],
        commands.Defend : [[self.defendRegression, 1], [self.botsInSightCone, 1]]
        }
        return classifier

    def initialize(self, classifier = {'None': None}, randomRate = 0.0):
        """Use this function to setup your bot before the game starts."""
        self.verbose = True    # display the command descriptions next to the bot labels
        self.counter = 0
        self.randomRate = 0.0
        self.bots = {}
        self.learningRate = .1
        self.discount = 1.0
        for bot in self.game.team.members:
            self.bots[bot] = {'currentAction': None, 'storedRegressionVector' : None,
                             'storedRegressionValueVector': None, 'forecastedValue' : None, 'timeOfAction': 0.0,
                              'dead': False
                              }
        # Classifier: Structured as {commands.Attack : (regression0, coefficient0), (regression1, coefficient1}... commands.Defend : (regression0.....)}
        self.actionClassifier = self.classifierGenerator()
        # Store all needed features.
        self.features = self.initialFeatureGenerator()
        
    def tick(self):
        """Routine to deal with new information every interval of about .1s"""
        self.featureUpdate()
        self.counter += 1
        for bot in self.game.team.members:
            #Decide if that bot's action is done or it has died and update the weight vector accordingly/issue a new action.
            resolved = self.testForActionResolved(bot)
            if resolved in ('died', 'finished'):
                print bot, 'actionEnded: ', resolved
                reward = self.getReward(bot)
                if resolved == 'finished':
                    (action, value, regressionVector, regressionValueVector) = self.getAction(bot)
                    self.issueAndStore(action, value, regressionVector, regressionValueVector)
                elif resolved == 'died':
                    self.updateWeights(bot, reward)
                    self.resetCurrentBotInfo(bot)
                #For finished and re-commanded, or dead bots, no need to check to see if the command interval has passed.
                continue
            #Every x ticks, check all bots for better commands than their current ones.
            elif self.counter % 50 == 0:
                (action, value, regressionVector, regressionValueVector) = self.getAction(bot)
                self.issueAndStore(action, value, regressionVector, regressionValueVector)

                
    def updateWeights(self, bot, reward):
        """Iterate over the weights used in the bot's last action, updating based on expected returns vs actual."""
        #If the currentAction is None, no action has yet been issued and there is no information to update. This happens early in games.
        if self.bots[bot]['currentAction'] == None:
            return
        command = self.bots[bot]['currentAction'][0]
        oldRegressions = self.bots[bot]['storedRegressionVector']
        regressions = self.actionClassifier[command]
        storedValueVector = self.bots[bot]['storedRegressionValueVector']
        forecastedValue = self.discount*self.bots[bot]['forecastedValue']
        presentBestActionValue = self.getPolicy(bot)[1]
        for index in range(len(regressions)):
            #We update each weight in the regression function vector.
            #This requires checking to see if the update we want to make has already been made by another bot.
            #We don't want to get the same update twice.
            oldWeight = oldRegressions[index][1]
            actualCurrentWeight = regressions[index][1]
            proposedNewWeight = \
            oldWeight + self.learningRate*storedValueVector[index]*(reward + presentBestActionValue - forecastedValue)
            proposedChange = proposedNewWeight - oldWeight
            changeFromOtherActionsBetweenCommandAndUpdate = actualCurrentWeight - oldWeight
            if proposedChange != 0.0:
                if changeFromOtherActionsBetweenCommandAndUpdate/proposedChange > .2:
                    continue
                else:
                    regressions[index][1] = proposedNewWeight       
        print self.actionClassifier[command]
        
    def getReward(self, bot):
        """Calculates how a finished action turned out for our bot. TODO learn reward values as opposed to hard? """
        killed = 1
        flagPickedUp = 2
        flagDropped = 3
        flagCaptured = 4
        flagRestored = 5
        botRespawned = 6        
        reward = 0
        for event in self.game.match.combatEvents:
            if self.bots[bot]['timeOfAction'] < event.time:
                #Did the bot die or kill something since it last committed to an action?
                if event.type == killed:
                    if event.subject == bot:
                        reward -= 50
                    elif event.instigator == bot:
                        reward += 10
                elif event.type == flagPickedUp:
                    if event.instigator == bot:
                        reward += 10
                elif event.type == flagCaptured:
                    if event.instigator == bot:
                        reward += 100              
        return reward
                
    def resetCurrentBotInfo(self, bot):
            self.bots[bot] = {'currentAction': None, 'storedRegressionVector' : None,
                             'storedRegressionValueVector': None, 'forecastedValue' : None, 'timeOfAction': 0.0,
                              'dead': False
                              }

    def testForActionResolved(self, bot):
        """Check if a given bot has either finished its action or died. Return True if yes, False if otherwise.
        This is used to tell when we update our weights, and when we give new orders out of cycle.
        """
        killed = 1
        if self.bots[bot]['dead'] == False or bot.health > 0:
            for event in self.game.match.combatEvents:
                #Did the bot die since it last committed to an action?
                if event.type == killed and self.bots[bot]['timeOfAction'] < event.time and event.subject == bot:
                    self.bots[bot]['dead'] = True
                    return 'died'
            if bot in self.game.bots_available:
                return 'finished'
            else:
                return False
        elif self.bots[bot]['dead'] == True:
            return False
 
    def getAction(self, bot):
        """
          Implements picking an action for a bot, allows for epsilon greedy exploration to be coded in.
          Returns value for issueAndStore to store for use in update function.
        """
        #Pick action either by exploring a random available option at a predetermined rate, or choosing amongst the best available options.
        legalActions = self.getCandidateActions(bot)
        if len(legalActions) == 0:
            (action, value, regressionVector, regressionValueVector) = (None, None, None, None)
        elif random.random() < self.randomRate == True:
            (action, value, regressionVector, regressionValueVector) = (random.choice(legalActions), None, None, None)
        else:
            (action, value, regressionVector, regressionValueVector)  = self.getPolicy(bot)
        return (action, value, regressionVector, regressionValueVector)

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
            (value, regressionVector, regressionValueVector) = self.getHueristicValue(bot, action)
            if value > bestValue:
                bestValue = value
                bestAction = action
                bestSet = []
                bestRegressionVector = regressionVector
                bestRegressionValueVector = regressionValueVector
            if value == bestValue:
                bestSet.append((action, value, regressionVector, regressionValueVector))          
        if len(bestSet) != 0:
            return random.choice(bestSet)
        return (bestAction, bestValue, bestRegressionVector, bestRegressionValueVector)

    def getCandidateActions(self, state):
        """Use random distribution across map to find potential points, add current action, defend facing a random set of directions.
        Alongside projected action by doing nothing."""
        bot = state
        actions = []
        for x in range(10):
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
        regressionValueVector = []
        for functionAndWeightPair in regressionVector:
            featureValue = functionAndWeightPair[0](bot, action)
            weight = functionAndWeightPair[1]
            singleFunctionValue = featureValue * weight
            value += singleFunctionValue
            regressionValueVector.append(featureValue)
        return (value, regressionVector, regressionValueVector)
        
    def getRegressionVector(self, command):
        vector = self.actionClassifier[command]
        return vector
        
    def issueAndStore(self, action, value, regressionVector, regressionValueVector):
        """Takes a list that constitutes a stored action, decides what kind of action it is,
        issues that command, tells commander bot is doing that command. We do this rather than directly
        issue so that currentAction can be a candidateAction. Also updates weights on issuing command."""        
        command = action[0]
        if command == 'currentAction':
            #Doing nothing continues current action. This is explicitly included for conceptual simplicity.
            return
        bot = action[1]
        reward = self.getReward(bot)
        self.updateWeights(bot, reward)
        if command == commands.Attack:
            self.issue(command, bot, action[2], description = action[3])
        elif command == commands.Defend:
            self.issue(command, bot, facingDirection = action[2], description=action[3])
        elif command == commands.Charge:
            self.issue(command, bot, description = action[2])
        elif command == commands.Move:
            self.issue(command, bot, description = action[2])            
        #Stores the action as the bots currently executing action.
        #Also store the regressions dict that picked it, the calculated value of the chosen action, and its time. 
        self.bots[bot]['currentAction'] = action
        self.bots[bot]['forecastedValue'] = value
        self.bots[bot]['storedRegressionVector'] = regressionVector
        self.bots[bot]['timeOfAction'] = self.game.match.timePassed
        self.bots[bot]['storedRegressionValueVector'] = regressionValueVector

    def shutdown(self):
        """Use this function to teardown your bot after the game is over, or perform an
        analysis of the data accumulated during the game."""

        pass
