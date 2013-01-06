# Your AI for CTF must inherit from the base Commander class.  See how this is
# implemented by looking at the commander.py in the ./api/ folder.
from api import Commander

# The commander can send 'Commands' to individual bots.  These are listed and
# documented in commands.py from the ./api/ folder also.
from api import commands

# The maps for CTF are layed out along the X and Z axis in space, but can be
# effectively be considered 2D.
from api import Vector2

import pickle, os, inspect, random, datetime

#My modules
import pythonDbHandler, regressions, regressions2, enemy_belief


class learningCommander(Commander):
    MODE_VISIBILITY = 0 
    MODE_TRAVELLING = 1
    
    def classifierGenerator(self):
        classifier = {
        commands.Attack : [[regressions2.enemy_shoots_path, -10],
                           [regressions.enemyFlag, 3],
                           [regressions.timeToScore, 100],
                           [regressions.lookTowardEnemyBots, -3],
                           [regressions.spread, -1],
                           [regressions.lookTowardEnemyBase, -1]
                           ],
        commands.Charge : [[regressions.botsInSightCone, 1],
                           [regressions.canEnemyBotSeePath, -1],
                           [regressions.timeToScore, 200]
                           ],
        commands.Move : [[regressions.enemyFlag, 1],
                         [regressions.botsInSightCone, 1],
                         [regressions.canEnemyBotSeePath, -1],
                         [regressions.timeToScore, 5]
                         ],
        commands.Defend : [[regressions.enemyFlag, 1],
                          [regressions.botsInSightCone, 1]
                          ]
                    }
        return classifier

    def initialize(self):
        """Use this function to setup your bot before the game starts."""
        #Initialized a graphical representation of work and the graph.
        #Makes 88x50 graph with adjacent squares having edges.
        #CALLS regressions2.makeGraph to do this.
        regressions2.initialize_graphics(self)
        regressions2.update_graph(self)

        #@test
        
        #Calculate initial probability distribution for location of enemies.
        enemy_belief.update_enemy_graph(self)
        
        self.verbose = True
        self.counter = 0
        #Used to store bots current command.
        self.bots = {}
        for bot in self.game.team.members:
            self.bots[bot.name] = {}
            self.bots[bot.name]["command"] = None
            
        # Classifier: Structured as {commands.Attack : (regression0, coefficient0), (regression1, coefficient1}... commands.Defend : (regression0.....)}
        self.classifier = self.classifierGenerator()

##        self.issue_initial()
        print 'DONE initializing'

    def issue_initial(self):
        for bot in self.game.team.members:
            a = commands.Attack(bot.name, self.game.enemyFlags[0].position, lookAt= self.level.findRandomFreePositionInBox(self.level.area), description = "TEST")
            
    def tick(self):
        """Routine to deal with new information every interval of about .1s"""
        
        self.counter += 1
        #Refreshes visuals
        if self.counter%15 == 0:
##            regressions2.update_graphics(self)
            enemy_belief.update_enemy_graph(self) 
            self.visualizer.tick()
            #Updates graph info
            regressions2.update_graph(self)

        test_enemy = self.game.enemyTeam.members[0]
        if self.counter % 20 == 0:
            pass
##            print "health: " , test_enemy.health
##            print "state: ", test_enemy.state
##            print "position: ", test_enemy.position
##            print "facingDirection: ", test_enemy.facingDirection

        for bot in self.game.team.members:
            
            #If it makes sense to move, evaluate actions and take the best. Otherwise don't waste processing power calculating an action.
            can_shoot_enemy, no_enemy_sighted = self.check_to_see_if_no_command(bot)
            if self.counter % 15 == 0 and can_shoot_enemy == False and bot.health > 0 or bot in self.game.bots_available:
                legalActions = self.get_p_actions(bot)
                command, value = self.get_action(bot, legalActions)
                
                #Consider whether the strength of continuing the current command and hence having no command wait is superior.
                #If it isn't, issue the command, otherwise, continue the present command.

                #Resets bots' stored commands to None who are dead or have finished a task.
                self.refresh_bot_commands()
                if self.bots[bot.name]["command"] != None:
                    continue_value = regressions2.evaluate_continue_present_command(self, bot, command)
                    if continue_value > value: #TODO calibrate skipping
                        continue
                self.issueCMD(command)
                
    def refresh_bot_commands(self):
        for bot in self.game.team.members:
            if bot.health < 0:
                self.bots[bot.name]["command"] = None
        for bot in self.game.bots_available:
            self.bots[bot.name]["command"] = None
            
    def check_to_see_if_no_command(self, bot):
        """Pass when any enemy is in our sights, or we don't see any enemies."""
        can_shoot_enemy = False
        no_enemy_sighted = True      
        #Check to see if no enemies are visible, or if the bot can currently shoot one.
        #In either case, this bot doesn't want a new order.
        for enemy_bot in self.game.enemyTeam.members:
            if enemy_bot.seenlast < 2.0 and enemy_bot.health > 0.0:
                no_enemy_sighted = False
                if regressions2.can_bot_shoot(self, bot, enemy_bot.position):
                    can_shoot_enemy = True                    
        return (can_shoot_enemy, no_enemy_sighted)
 
    def get_action(self, bot, legalActions):
        """Adds layer of flexibility used to get better look angles."""
        command, value = self.get_policy(bot, legalActions)
        legalActions = self.getLookDirectionArray(15, command)
        command, value = self.get_policy(bot, legalActions)
        return command, value
        
    def get_policy(self, bot, candidateActions):
        """
          Compute the best command to take for a given bot by getting all values, choosing highest.
          Return command, valuation of command, regression vector used to get valuation.
        """
        bestAction = None
        bestValue = float("-inf")
        bestSet = []
        for command in candidateActions:
            value = self.get_hueristic_value(bot, command)
            if value == bestValue:
                bestSet.append(command) 
            elif value > bestValue:
                bestValue = value
                bestAction = command
                bestSet = []       
        if len(bestSet) != 0:
            return random.choice(bestSet), bestValue
        return bestAction, bestValue

    def get_p_actions(self, bot): #TODO, random map filter, generate new points about best N commands, pick best from secondary filter.
        command_list = []
        #Enemy Flag
        destination = self.game.enemyFlags[0].position
        waypoints = regressions2.get_path(self, bot.position, destination)
        direction = self.level.findRandomFreePositionInBox(self.level.area)
        command_list.append(commands.Attack(bot.name, waypoints, lookAt = direction, description = "Attacking selected point."))
        #Score location
        destination = self.game.team.flagScoreLocation
        waypoints = regressions2.get_path(self, bot.position, destination)
        direction = self.level.findRandomFreePositionInBox(self.level.area)
        command_list.append(commands.Attack(bot.name, waypoints, lookAt = direction, description = "Attacking selected point."))

        #Update graph before calculating all new paths.
        for x in range(15):
            #Add random attack destinations
            destination = self.level.findRandomFreePositionInBox(self.level.area)
            waypoints = regressions2.get_path(self, bot.position, destination)
            
            direction = self.level.findRandomFreePositionInBox(self.level.area) 
            command_list.append(commands.Attack(bot.name, waypoints, lookAt = direction, description = "Attacking selected point."))
        return command_list

    def getLookDirectionArray(self, numActions, command):
        """Returns an arbitrary length list of commands based on the passed command with random look directions."""
        newActionList = []
        if type(command) == commands.Attack:
            for x in range(numActions):
                direction = self.level.findRandomFreePositionInBox(self.level.area)
                command.lookAt = direction
                newActionList.append(command)
        elif type(command) == commands.Defend:
            for x in range(numActions):
                direction = Vector2(random.random()*random.sample([-1,1],1)[0], random.random()*random.sample([-1,1],1)[0])
                command.facingDirection = direction
                newActionList.append(command)
        return newActionList

    def get_hueristic_value(self, bot, command):
        #Takes bot, command, uses self.classifier dict to return a valuation of the bot's command.
        value = 0
        regressionVector = self.classifier[type(command)]
        for functionAndWeightPair in regressionVector:
            featureValue = functionAndWeightPair[0](self, bot, command)
            weight = functionAndWeightPair[1]
            singleFunctionValue = featureValue * weight
            value += singleFunctionValue
        return value

    def issueCMD(self, command):
        bot = self.game.team.members[int(command.botId[-1])]
        #Store command
        self.bots[bot.name]["command"] = command
        
        if type(command) == commands.Attack:
            self.issue(type(command), bot, command.target, lookAt = command.lookAt, description = command.description)
        elif type(command) == commands.Defend:
            self.issue(type(command), bot, facingDirection = command.facingDirection, description = command.description)
        elif type(command) == commands.Charge:
            self.issue(type(command), bot, command.target, description = command.description)
        elif type(command) == commands.Move:
            self.issue(type(command), bot, command.target, description = command.description)

    def shutdown(self):
        pass
