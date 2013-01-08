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


class hodorCommander(Commander):
    MODE_VISIBILITY = 0 
    MODE_TRAVELLING = 1
    
    def classifierGenerator(self):
        classifier = {
        commands.Attack : [[regressions2.go_toward_flag, -2],
                           [regressions2.enemy_distance, -7],
                           [regressions2.time_to_score, -120000],
                           ],
        commands.Charge : [[regressions2.go_toward_flag, -1],
                           [regressions2.time_to_score, -100000],
                           [regressions2.enemy_distance, -4]
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
        self.GRAPHICS = True
        #Initialized a graphical representation of work and the graph.
        #Makes 88x50 graph with adjacent squares having edges.
        #CALLS regressions2.make_graph to do this.
        regressions2.make_graph(self)
        regressions2.update_graph(self)

        if self.GRAPHICS:
            regressions2.initialize_graphics(self)        
            #Calculate initial probability distribution for location of enemies.
            #Show initial gui graphics.
            regressions2.update_graphics_probability(self, mode = "p_enemy")
            self.visualizer.tick()
        
        self.verbose = True
        self.counter = 0
        
        #Used to store bots current command.
        self.bots = {}
        for bot in self.game.team.members:
            self.bots[bot.name] = {}
            self.bots[bot.name]["command"] = None
            
        # Classifier: Structured as {commands.Attack : (regression0, coefficient0), (regression1, coefficient1}... commands.Defend : (regression0.....)}
        self.classifier = self.classifierGenerator()
        print 'DONE initializing'
            
    def tick(self):
        """Routine to deal with new information every interval of about .1s"""
        
        self.counter += 1

        if self.counter == 1:
            regressions2.update_graph(self)
            self.graphics_tick()            
            self.command_routine()

        if self.counter % 20 == 0:
            #Updates graph knowledge about game state.
            regressions2.update_graph(self)
            #Update graphics to show probability distribution of enemies' as we assess it.
            #Optionally we can pass any of the probabilities weighted on the graph : p_enemy, p_enemy_fire, p_enemy_sight.     
            self.command_routine()

            self.graphics_tick()

    def graphics_tick(self):
        if self.GRAPHICS == True:
            regressions2.update_graphics_probability(self, mode = "p_enemy_fire") 
            self.visualizer.tick()      
        
            
    def command_routine(self):
        for bot in self.game.team.members:           
            #If it makes sense to move, evaluate actions and take the best. Otherwise don't waste processing power calculating an action.
            no_command = self.check_to_see_if_no_command(bot)
            if no_command == False and bot.health > 0 or bot in self.game.bots_available:
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
                self.issue_cmd(command)
                
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
        return can_shoot_enemy
 
    def get_action(self, bot, legalActions):
        """Adds layer of flexibility used to get better look angles."""
        command, value = self.get_policy(bot, legalActions)
##        legalActions = self.get_look_direction_array(5, command)
##        command, value = self.get_policy(bot, legalActions)
        return command, value
        
    def get_policy(self, bot, candidate_actions):
        """
          Compute the best command to take for a given bot by getting all values, choosing highest.
          Return command, valuation of command, regression vector used to get valuation.
        """
        bestAction = None
        bestValue = float("-inf")
        bestSet = []
        for command in candidate_actions:
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
        destination = self.game.enemyTeam.flag.position
        direction = self.level.findRandomFreePositionInBox(self.level.area)
        waypoints = regressions2.get_path(self, bot.position, destination)
        waypoints = self.prune_waypoints(waypoints)
        command = self.get_view_command(commands.Attack(bot.name, waypoints, lookAt = direction, description = "Attacking the flag at %s." % str(waypoints[-1])))
        command_list.append(command)
        
        #Score location
        destination = self.game.team.flagScoreLocation
        waypoints = regressions2.get_path(self, bot.position, destination)
        waypoints = self.prune_waypoints(waypoints)
        command = self.get_view_command(commands.Charge(bot.name, waypoints, description = "Attacking our flag score point at %s." % str(waypoints[-1])))
        command_list.append(command)

        #Update graph before calculating all new paths.
        for x in range(4):
            #Add random attack destinations
            direction = self.level.findRandomFreePositionInBox(self.level.area) 
            destination = self.level.findRandomFreePositionInBox(self.level.area)
            waypoints = regressions2.get_path(self, bot.position, destination)
            #Shorten waypoint list to speed up calculations by factor of 3.
            waypoints = self.prune_waypoints(waypoints)
            command = self.get_view_command(commands.Attack(bot.name, waypoints, lookAt = direction, description = "Attacking toward the enemy."))
            command_list.append(command)

            destination = self.level.findRandomFreePositionInBox(self.level.area)
            waypoints = regressions2.get_path(self, bot.position, destination)
            waypoints = self.prune_waypoints(waypoints)
            command_list.append(commands.Charge(bot.name,waypoints, description = "Charging toward the enemy."))
        return command_list

    def get_view_command(self, command):
        bot = self.game.team.members[int(command.botId[-1])]
        final_direction = command.target[-1]        
        influence_vector = Vector2(0, 0)

        total_count = 0.0
        for node_index in self.graph.nodes():
            p_enemy = self.graph.node[node_index]["p_enemy"]
            if p_enemy != 0.0:
                node_vector = regressions2.get_node_vector(self, node_index)
                influence_vector += node_vector/(node_vector.distance(bot.position)+1)*p_enemy
                total_count += 1/(node_vector.distance(bot.position)+1)*p_enemy
        
        if influence_vector.length() != 0.0:
            influence_vector /= total_count
            final_direction = influence_vector
            
        if type(command) == commands.Attack:
            command.lookAt = final_direction
            
        elif type(command) == commands.Defend:
            final_direction = final_direction - bot_position
            final_direction.normalize()
            command.facingDirection = final_direction
        return command
                    

    def prune_waypoints(self, waypoints):
        length = len(waypoints)
        if length > 4:
            waypoints = waypoints[::int(length)/4]
        return waypoints

    def get_look_direction_array(self, numActions, command):
        """Returns an arbitrary length list of commands based on the passed command with random look directions."""
        newActionList = []
        newActionList.append(command)
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

    def issue_cmd(self, command):
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



    
