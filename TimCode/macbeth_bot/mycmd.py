# Your AI for CTF must inherit from the base Commander class.  See how this is
# implemented by looking at the commander.py in the ./api/ folder.
from api import Commander

# The commander can send 'Commands' to individual bots.  These are listed and
# documented in commands.py from the ./api/ folder also.
from api import commands

# The maps for CTF are layed out along the X and Z axis in space, but can be
# effectively be considered 2D.
from api import Vector2

#Third party
import networkx as nx

import pickle
import os
import inspect
import random
import datetime

#My modules
import regressions
import regressions2
import enemy_belief
import spawn_camp

PRINT = False
UNIT_TEST = False
TRAINING = False
LOAD = False
if TRAINING or LOAD:
    import pythonDbHandler

class macbethCommander(Commander):
    MODE_VISIBILITY = 0 
    MODE_TRAVELLING = 1
    
    def classifierGenerator(self):
        if LOAD:
            classifier = pythonDbHandler.loadClassifier(22)
            print classifier
        elif TRAINING:
            print "LOADING BOT"
            classifier = self.get_classifier_from_env()
        else:
            print "USING STOCK BOT"
            classifier = {commands.Charge: [#[regressions2.max_angles, 0.0],
            [regressions2.go_to_camp, 1.0],
            [regressions2.go_to_flank_brink, 15.0],
            [regressions2.spread_targets2, 1.0],
            [regressions2.camp_strategy_go_toward_flag, 2.0],
            [regressions2.enemy_distance, 10.0],
            [regressions2.friendly_to_enemy_ratio, 5.0],
            [regressions2.max_angles, 20.0],
            [regressions2.spread_targets2, 1.0]
            ],

            commands.Attack: [#[regressions2.max_angles, 0.0],
            [regressions2.go_to_camp, 1.0],
            [regressions2.go_to_flank_brink, 15.0],
            [regressions2.spread_targets2, 1.0],
            [regressions2.camp_strategy_go_toward_flag, 1.0],
            [regressions2.enemy_distance, 10.0],
            [regressions2.friendly_to_enemy_ratio, -5.0],
            [regressions2.max_angles, 20.0],
            [regressions2.spread_targets2, 1.0]
            ],

            commands.Move : [],

            commands.Defend : [[regressions2.evaluate_camp_command, 1000.0],
                               [regressions2.lower_redundant_camp_value, 20.0]]
            }
            
        return classifier

    def initialize(self):
        """Use this function to setup your bot before the game starts."""
        self.points = []
        self.verbose = True
        self.counter = 0
        self.enemies = {}
        self.botID = None
        self.HOLD_RATE = 10
        self.COMMAND_RATE = 35
        self.AVAIL_RATE = 3
        self.SUICIDE_CHECK_RATE = 4
        #Number of ticks between storage of enemy position for extrapolation.
        self.EXTRAP_STORE_RATE = 15

        #Used to tell whether the bot is calculating actions.
        self.computing = False
        
        #Used to store bots current command.
        self.bots = {}
        for bot in self.game.team.members:
            self.bots[bot.name] = {}
            self.bots[bot.name]["command"] = None
            self.bots[bot.name]["last_command_time"] = -5.0
            self.bots[bot.name]["visibility"] = set()
            
        # Classifier: Structured as {commands.Attack : (regression0, coefficient0), (regression1, coefficient1}... commands.Defend : (regression0.....)}
        self.classifier = self.classifierGenerator()

        #GRAPHICS LOGIC     
        #Toggles graphics to desired display. Must be off to submit!!!
##        self.GRAPHICS = "p_enemy"
##        self.GRAPHICS = "p_enemy_sight"
##        self.GRAPHICS = "p_enemy_fire"
##        self.GRAPHICS = "ambush"
##        self.GRAPHICS = "pheremone"      
##        self.GRAPHICS = "exit_path"
##        self.GRAPHICS = "camp_target"
##        self.GRAPHICS = "choke_covered"
##        self.GRAPHICS = "camp_location"
        
        self.GRAPHICS = False
        
        #Toggles drawing helper points.
##        self.DRAW_POINTS = "extrap"
        self.DRAW_POINTS = "flanking"
##        self.DRAW_POINTS = "camp"
##        self.DRAW_POINTS = False
        
        #Refactoring functional self variables here for easy tweaking.
        #At what distance do we cut off speculation on an enemy's location?
        self.MAX_ENEMY_DISTANCE = 25
        #Variable used in enemy_belief to determine how many points to do sight calcs on. 
        self.TOTAL_FS_NODES = 13
        #Determines minimum probability of an enemy being in a node for it to be evaluated.
        self.MINIMUM_ENEMY_PROB = 0.01
        
        #Initialized a graphical representation of work and the graph.
        #Makes 88x50 graph with adjacent squares having edges.
        #CALLS regressions2.make_graph to do this.
        regressions2.make_graph(self)
##        regressions2.calculate_control_main_route2(self)
        self.camp_positions = spawn_camp.calculate_spawn_camp(self)
        regressions2.update_graph(self)
        
        if self.GRAPHICS or self.DRAW_POINTS:
            regressions2.initialize_graphics(self)   
            #Calculate initial probability distribution for location of enemies.
            #Show initial gui graphics.
            regressions2.update_graphics_probability(self, mode = self.GRAPHICS)
            self.visualizer.tick()

        print 'DONE initializing'
            
    def tick(self):
        """Routine to deal with new information every interval of about .1s"""
        self.counter += 1
        #Don't act if we are still in the process of issuing commands from a previous tick.
##        if self.computing == False:
        self.HOLD_RATE = 7
        self.COMMAND_RATE = 35
        self.AVAIL_RATE = 8
        self.SUICIDE_CHECK_RATE = 15
        #Number of ticks between storage of enemy position for extrapolation.
        self.EXTRAP_STORE_RATE = 10

        if self.counter%self.COMMAND_RATE != 0.0 and self.counter%self.EXTRAP_STORE_RATE == 0:
            #Keep track of where enemies are this tick so we can extrapolate later.
            enemy_belief.store_enemy_positions(self)
            
        #Ensure our info doesn't get too outdated. Every half cycle update for benefit of hold/ avail commands.
        if (self.counter + int(self.COMMAND_RATE)/4)% self.COMMAND_RATE == 0:
            regressions2.update_graph(self)
            
        if self.counter == 1:
            #We do this twice even though we plan to override it. We want a point to spread our targets from.
            self.command_routine(self.game.team.members)
            self.graphics_tick()

        if self.counter%self.SUICIDE_CHECK_RATE == 0:
            print "AVOIDING DEATH"
            self.avoid_suicide_and_trades()

        if self.counter%self.AVAIL_RATE == 0:
            if self.counter%self.COMMAND_RATE != 0 and self.counter%self.HOLD_RATE != 0 and self.SUICIDE_CHECK_RATE != 0:
                for bot in self.game.bots_available:
                    #Updates graph knowledge about game state.
                    #Update graphics to show probability distribution of enemies' as we assess it.
                    #Optionally we can pass any of the probabilities weighted on the graph : p_enemy, p_enemy_fire, p_enemy_sight.     
                    self.command_routine([bot])
                    self.graphics_tick()

        if self.counter%self.HOLD_RATE == 0:
            if len(self.game.bots_holding) > 0 and self.counter%self.COMMAND_RATE != 0 and self.counter%self.AVAIL_RATE !=0 and self.SUICIDE_CHECK_RATE != 0:
                #Updates graph knowledge about game state.
                #Update graphics to show probability distribution of enemies' as we assess it.
                #Optionally we can pass any of the probabilities weighted on the graph : p_enemy, p_enemy_fire, p_enemy_sight.     
                self.command_routine(self.game.bots_holding)
                self.graphics_tick()
        
        if self.counter % self.COMMAND_RATE == 0 and self.SUICIDE_CHECK_RATE != 0 and self.counter%self.AVAIL_RATE !=0:
            #Updates graph knowledge about game state.
            regressions2.update_graph(self)
            #Update graphics to show probability distribution of enemies' as we assess it.
            #Optionally we can pass any of the probabilities weighted on the graph : p_enemy, p_enemy_fire, p_enemy_sight.     
            self.command_routine(self.game.team.members)
            self.graphics_tick()

    def avoid_suicide_and_trades(self):
        #New orders for all charging bots about to suicide.
        if self.counter%self.COMMAND_RATE != 0 and self.counter%self.AVAIL_RATE !=0 and self.counter%self.HOLD_RATE != 0:
            bots = []
            for bot in self.game.team.members:
                if bot.health > 0 and self.bots[bot.name]["command"] != None:
                    if type(self.bots[bot.name]["command"]) == commands.Charge or type(self.bots[bot.name]["command"]) == commands.Attack:
                        continue_command = regressions2.get_continue_command(self, bot, self.bots[bot.name]["command"])
                        if len(continue_command.target) == 1:
                            if self.graph.node[regressions2.get_node_index(self, continue_command.target[0])]["p_enemy_fire"] > .4:
                                bots.append(bot)
                        else:
                            for position in continue_command.target[0:int(len(continue_command.target)/2)]:
                                if self.graph.node[regressions2.get_node_index(self, position)]["p_enemy_fire"] > .4:
                                    bots.append(bot)
            self.command_routine(bots)
            

    def graphics_tick(self):
        if self.GRAPHICS:
            regressions2.update_graphics_probability(self, mode = self.GRAPHICS) 
            self.visualizer.tick()
        elif self.DRAW_POINTS:
            regressions2.draw_points(self, self.points)
            self.visualizer.tick()
            self.visibilities.fill(0)
        
            
    def command_routine(self, bots):
        self.computing = True
        for bot in bots:
            #If it makes sense to move, evaluate actions and take the best. Otherwise don't waste processing power calculating an action.
            no_command = self.check_to_see_if_no_command(bot)
            if no_command == True:
                continue
            elif bot.health > 0:
                legalActions = self.get_p_actions(bot)
                command, value = self.get_action(bot, legalActions)
                if type(command) == commands.Defend:
                    command = spawn_camp.get_camp_command(self, bot, command)
                else:
                    command = self.get_view_command(command)
                    self.register_waypoints(bot, command.target)
                #Resets bots' stored commands to None who are dead or have finished a task.
                self.refresh_bot_commands()
##                if self.bots[bot.name]["command"] != None:
##                    continue_value = regressions2.evaluate_continue_present_command(self, bot, command)
##                    if continue_value > value: #TODO calibrate skipping
##                        continue
                self.bots[bot.name]["last_command_time"] = self.game.match.timePassed
                command.description = "%s:  %d" % (str(type(command))[21], value)
                self.issue_cmd(command)
        self.computing = False
                
    def refresh_bot_commands(self):
        for bot in self.game.team.members:
            if bot.health <= 0.0:
                self.bots[bot.name]["command"] = None
        for bot in self.game.bots_available:
            self.bots[bot.name]["command"] = None
            
    def check_to_see_if_no_command(self, bot):
        """Pass when any enemy is in our sights, or we don't see any enemies."""
        can_shoot_enemy = False
        enemy_sighted = False
        recent_command = False
        #Check to see if no enemies are visible, or if the bot can currently shoot one.
        #In either case, this bot doesn't want a new order.
        for enemy_bot in self.game.enemyTeam.members:
            if enemy_bot.seenlast < 2.0 and enemy_bot.health > 0.0 and enemy_bot in bot.visibleEnemies:
                if regressions2.can_bot_shoot(self, bot, enemy_bot.position):
                    can_shoot_enemy = True
        if can_shoot_enemy:
            return True
        else:
            return False
 
    def get_action(self, bot, legalActions):
        """Adds layer of flexibility used to get better look angles."""
        command, value = self.get_policy(bot, legalActions)
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
            #Get action value and discount by time.
            value = self.get_hueristic_value(bot, command) * 10/(10 + self.get_command_time(bot, command))
            if value == bestValue:
                bestSet.append(command) 
            elif value > bestValue:
                bestValue = value
                bestAction = command
                bestSet = []       
        if len(bestSet) != 0:
            return random.choice(bestSet), bestValue
        return bestAction, bestValue

    def get_flanking_positions(self, bot, actions = 10):
        position_list = []
        for x in range(actions * 10):
            position = self.level.findRandomFreePositionInBox(self.level.area)
            score = self.score_flanking_position(position, bot)
            position_list.append((score, position))
        position_list.sort()
        position_list = position_list[len(position_list) - actions:-1]
        return_list = [position for score, position in position_list]
        return return_list

    def score_flanking_position(self, position, bot):
        #Score possible positions
        node_index = regressions2.get_node_index(self, position)        
        they_can_shoot = self.graph.node[node_index]["p_enemy_fire"]
        
        far_from_friendlies = 0
        for friendly in self.game.team.members:
            if friendly.health > 0.0:
                command = self.bots[friendly.name]["command"]
                if command != None and type(command) != commands.Defend:
                    far_from_friendlies += position.distance(command.target[-1])
        far_from_friendlies /= len(self.game.team.members)
            
        rough_enemy_dist = 0.0
        living = 0.0
        for enemy_bot in self.game.enemyTeam.members:
            if enemy_bot.health > 0.0:
                living += 1
                rough_enemy_dist += position.distance(enemy_bot.position)
        rough_enemy_dist /= living+1

        goto_flank_brink = 0.0
        try:
            minimum_distance = min([position.distance(enemy_bot.position) for enemy_bot in self.game.enemyTeam.members if enemy_bot.health > 0.0])
        except ValueError: #If the enemy are all dead, set their position is far away.
            minimum_distance = 100
        dist_from_flank_range = abs((self.level.firingDistance) - minimum_distance)
        if dist_from_flank_range > -1:
            goto_flank_brink = 50/(dist_from_flank_range**1.5+1)


        average_friendly_dist = 0.0
        friendlies = 0.0
        for friendly in self.game.team.members:
            if friendly.health > 0.0 and friendly != bot:
                friendlies += 1
                average_friendly_dist += position.distance(friendly.position)
        average_friendly_dist /= (friendlies+1)
        
        if average_friendly_dist > rough_enemy_dist:
            past_enemy = 50
        else:
            past_enemy = 0.0
        
        a, b, c, d, e = far_from_friendlies*20, goto_flank_brink*50, they_can_shoot*-500, rough_enemy_dist*-20, past_enemy*-50
        
##        print "far_from_friendlies: ", a
##        print "goto_flank_brink: ", b 
##        print "they_can_shoot: ", c
##        print "rough_enemy_dist: ", d
##        print "distance: ", e
##        print 
        score = a + b + c + d + e
        return score

    def get_potential_camp_positions(self, bot, actions = 5):
        return_list = []
        for x in range(actions):
            position = random.choice(self.camp_positions)
            return_list.append(position)

##        remove_list = [] #TODO - fix
##        for camp_position in return_list:
##            p = 1.0
##            for friendly in self.game.team.members:
##                if bot.position.distance(friendly.position) < 5.0:
##                    p *= .8
##            if random.random() > p:
##                remove_list.append(camp_position)
##
##        for remove_position in remove_list:
##            if len(return_list) > 1:
##                return_list.remove(remove_position)    
        return return_list
    
    def get_p_actions(self, bot): #TODO, random map filter, generate new points about best N commands, pick best from secondary filter.
        command_list = []

        #If our bot has the flag... don't run toward the enemy, go score!
        if bot.flag:
            #Score location
            destination = self.game.team.flagScoreLocation
            regressions2.update_score_graph(self)
            waypoints = regressions2.get_path(self, bot.position, destination)
            waypoints = self.prune_waypoints(waypoints)
            command_list.append(commands.Move(bot.name, waypoints, description = "Moving toward the flag score."))
            regressions2.update_graph(self)
            return command_list      

        #Random
        target = self.level.findRandomFreePositionInBox(self.level.area)
        waypoints = regressions2.get_path(self, bot.position, target)
        command_list.append(commands.Attack(bot.name, waypoints, description = "Attacking to random position"))
        
        potential_flanking_positions = self.get_flanking_positions(bot, actions = 6)
        potential_charge_flank = potential_flanking_positions[len(potential_flanking_positions)/2:-1]
        
        if self.DRAW_POINTS == "flanking":
            regressions2.draw_points(self, potential_flanking_positions) 

        #Defend
        redundancy = 0
        friendlies = regressions2.get_friendlies_in_range(self, bot.position, 2)
        campers = 0
        for friendly in friendlies:
            if friendly.state == 2:
                redundancy += 1
        if redundancy < 3 and len(friendlies) <= 3:  
            defend_command = commands.Defend(bot.name)
            command_list.append(defend_command)

        living_enemies = 0
        for enemy in self.game.enemyTeam.members:
            if enemy.health > 0:
                living_enemies += 1
        if len(self.game.bots_alive)/(living_enemies+1) > 1.3 or (bot.position - self.game.enemyTeam.flag.position).length() < 30:
            #Enemy Flag - ATTACK AND CHARGE
            destination = self.game.enemyTeam.flag.position
            direction = self.level.findRandomFreePositionInBox(self.level.area)
            waypoints = regressions2.get_path(self, bot.position, destination)
            waypoints = self.prune_waypoints(waypoints)
            command_list.append(commands.Attack(bot.name, waypoints, description = "Attacking toward enemy flag."))            
        if len(self.game.bots_alive)/(living_enemies+1) > 1.5 or (bot.position - self.game.enemyTeam.flag.position).length() < 25:
            command_list.append(commands.Charge(bot.name, waypoints, description = "Charging toward the enemy flag."))


        for position in potential_flanking_positions:
            destination = position
            waypoints = regressions2.get_path(self, bot.position, destination)
            #Shorten waypoint list to speed up calculations.
            waypoints = self.prune_waypoints(waypoints)
            command_list.append(commands.Attack(bot.name, waypoints, description = "Flanking toward the enemy at %s." % waypoints[-1]))
            
        for position in potential_charge_flank:
            destination = position
            waypoints = regressions2.get_path(self, bot.position, destination)
            waypoints = self.prune_waypoints(waypoints)
            command_list.append(commands.Charge(bot.name, waypoints, description = "Charging toward the enemy at %s." % waypoints[-1]))

        if bot.position.distance(self.level.botSpawnAreas[self.game.enemyTeam.name][0]) < 15:
            potential_camp_positions = self.get_potential_camp_positions(bot, actions = 10)
            for destination in potential_camp_positions:
                skip_tail = False
                for bot_name in self.bots.keys(): #TODO fix based on distance.
                    #No duplicate destinations.
                    command = self.bots[bot_name]["command"]
                    if command != None:
                        friendly = self.get_bot_from_command(command)
                        if friendly == bot:
                            skip_tail = True
                            break
                        if type(command) == commands.Defend and friendly.position.distance(destination) < 1.0:
                            skip_tail = True
                            break
                        if type(command) != commands.Defend:
                            if self.bots[bot_name]["command"].target[-1].distance(destination) < 1.0:
                                skil_tail = True
                                break     
                if not skip_tail:
                    command = self.build_command(bot, destination, commands.Attack)
                    command_list.append(command)
                    command = self.build_command(bot, destination, commands.Charge)
                    command_list.append(command)

        return command_list

    def build_command(self, bot, target, mode):
        waypoints = regressions2.get_path(self, bot.position, target)
        waypoints = self.prune_waypoints(waypoints)
        command = mode(bot.name, waypoints)
        return command
                   

    def get_bot_from_command(self, command):
        bot_index = command.botId
        if bot_index.find("Red") >= 0:
            bot_index = bot_index[3:]
        elif bot_index.find("Blue") >= 0:
            bot_index = bot_index[4:]
        bot_index = int(bot_index)
        bot = self.game.team.members[bot_index]
        return bot
    
    def get_bot_from_name(self, bot_index):
        if bot_index.find("Red") >= 0:
            bot_index = bot_index[3:]
        elif bot_index.find("Blue") >= 0:
            bot_index = bot_index[4:]
        bot_index = int(bot_index)
        bot = self.game.team.members[bot_index]
        return bot

    def get_view_command(self, command):
        bot = self.get_bot_from_command(command)
        bot_position = bot.position
        
        if type(command) == commands.Attack:
            nodes = self.graph.nodes()
            total_mass = 0.0
            
            first_position = regressions2.get_node_vector(self, nodes[0])
            first_mass = self.graph.node[nodes[0]]["p_enemy"] * 1/(bot_position.distance(first_position)**2+1)

            center = first_position * first_mass
            total_mass += first_mass

            for node_index in nodes[1:]:
                prob = self.graph.node[node_index]["p_enemy"]
                node_position = regressions2.get_node_vector(self, node_index)
                distance = bot_position.distance(node_position)
                mass = 1/((distance)**2+1) * prob
                #Prevent very close, low probability enemies from biasing.
##                if prob < .2 and distance < 8:
##                    continue
                center += node_position * mass
                total_mass += mass

            if total_mass != 0.0:
                final_vector = center/total_mass
            else:
                final_vector = command.target[-1]
            command.lookAt = final_vector
            #TODO weight direction of travel into vector?
        return command

    def register_waypoints(self, bot, waypoints):
        edges = []
        edges.append((bot.position, waypoints[0]))
        for waypoint_index in range(len(waypoints)-1):
            edges.append((waypoints[waypoint_index], waypoints[waypoint_index+1]))
        total_nodes = set()
        for edge in edges:
            source_node = regressions2.get_node_index(self, edge[0])
            target_node = regressions2.get_node_index(self, edge[1])
            path = nx.shortest_path(self.graph, source=source_node, target=target_node)
            for node in path:
                total_nodes.add(node)                
        for node_index in total_nodes:
            self.graph.node[node_index]["pheremone"] += 1
            neighbors = self.graph.neighbors(node_index)
            if neighbors is not None:
                for neighbor_index in neighbors:
                    self.graph.node[neighbor_index]["pheremone"] += .5
                    neighbors2 = self.graph.neighbors(neighbor_index)
                    if neighbors2 is not None:
                        for neighbor_index2 in neighbors2:
                            self.graph.node[neighbor_index]["pheremone"] += .2            

    def prune_waypoints(self, waypoints):
        length = len(waypoints)
        #Last waypoint is important as it is used for calculations.
        last = waypoints[-1]
        if length > 8:
            waypoints = waypoints[3::6] + [last]
        elif len(waypoints) > 3:
            waypoints = waypoints[2::] + [last]
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
        if PRINT:
            print type(command)
        regressionVector = self.classifier[type(command)]
        for function, weight in regressionVector:
            featureValue = function(self, bot, command)
            singleFunctionValue = featureValue * weight
            value += singleFunctionValue
            if PRINT:
                print function.__name__, '   value: ', singleFunctionValue #@PRINT
        if PRINT:
            print
        return value

    def issue_cmd(self, command):
        bot = self.get_bot_from_command(command)
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
            
    def get_command_time(self, bot, command):
        if type(command) in [commands.Charge, commands.Move]:
            speed = self.level.runningSpeed
            distance = bot.position.distance(command.target[0])
            for index in range(len(command.target)-1):
                position1 = command.target[index]
                position2 = command.target[index+1]
                distance = position1.distance(position2)
            time = distance/speed + 1
            
        elif type(command) == commands.Attack:
            speed = self.level.walkingSpeed
            distance = bot.position.distance(command.target[0])
            for index in range(len(command.target)-1):
                position1 = command.target[index]
                position2 = command.target[index+1]
                distance = position1.distance(position2)
            time = distance/speed + 1
        elif type(command) == commands.Defend:
            time = 1
        return time              
    
    def get_classifier_from_env(self):
        if self.game.team.name == 'Red':
            botID = int(os.environ['red_team_bot_id'])
            classifier = pythonDbHandler.loadClassifier(botID)
        elif self.game.team.name == 'Blue':
            botID = int(os.environ['blue_team_bot_id'])
            classifier = pythonDbHandler.loadClassifier(botID)
        if classifier != None:
            self.botID = botID	
            return classifier

    def shutdown(self):
        print 'SHUTTING DOWN AND STORING'
        if self.botID:
            pythonDbHandler.storeClassifier(self.classifier, self.botID)
