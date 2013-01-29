import math, itertools, random
from api import vector2, Vector2, commands
#Third party modules
import networkx as nx
#KILLZONE modules
import visibility
#From twilder
import regressions2

def update_enemy_graph(instance):
    regressions2.reset_graph(instance)
    known_enemies = get_known_enemies(instance)
    #Find last known whereabouts and condition of each enemy bots
    at_large_enemies = get_at_large_enemies(instance, known_enemies)
    
    #Get linear extrapolations of enemy movement
    bot_extraps = extrapolate(instance)
    store_enemy_positions(instance)
    
    #Account for at large enemies list complete with last seen positions and times of all unseen enemies.
    bot_nodes_list = [] # Stores info on which bot accounted for which nodes.
    for enemy_bot in at_large_enemies:
        #Skip if the information is very stale.
        if enemy_bot.seenlast > 25.0:
            continue    
        #Based on these variables, calculate nodes that the bot could occupy.
        nodes = get_nodes_for_one_enemy(instance, enemy_bot)
        set_probability_density(instance, nodes, enemy_bot.position, enemy_bot, bot_extraps)        
        bot_nodes_list.append((enemy_bot, nodes))

    #Account for position and probability of all definitively known enemies.
    known_enemy_nodes = set()
    for enemy_bot in known_enemies:
        #Enemy could be at start of game.
        node_index = regressions2.get_node_index(instance, enemy_bot.position)
        known_enemy_nodes.add(node_index)
        instance.graph.node[node_index]["friendly_sight"] = True
        instance.graph.node[node_index]["p_enemy"] = 1.0
        nodes = [node_index]
        bot_nodes_list.append((enemy_bot, nodes))

    #Set sight and cone of fire data based on all nodes enemy_bots could be present in.
    for enemy_bot, nodes in bot_nodes_list:
        set_fs_density(instance, nodes, enemy_bot)
    print "DONE UPDATING ENEMY GRAPH"

##############################################################################################################
#                          Discover Enemy Last Seen Positions Accounting for Spawns                          #
##############################################################################################################

def get_known_enemies(instance):
    #List enemies we have 100% certain location knowledge on.
    known_enemies = []
    for bot in instance.game.team.members:
        for enemy_bot in bot.visibleEnemies:
            if enemy_bot.health > 0.0:
                if enemy_bot not in known_enemies:
                    known_enemies.append(enemy_bot)
    #List enemies we are pretty sure of.
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.health > 0.0 and enemy_bot.seenlast < .2:
            known_enemies.append(enemy_bot)
    return known_enemies    

def get_at_large_enemies(instance, known_enemies):
    #List enemies without 100% certainty of location.
    #Format is bot, last known position.
    unknown_enemies = []
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot not in known_enemies and enemy_bot not in unknown_enemies:
            if enemy_bot.health > 0:
                unknown_enemies.append(enemy_bot)
    return unknown_enemies
            
##############################################################################################################
#                          Calculate the Squares a Given Enemy Could possible Occupy                         #
##############################################################################################################

#Initially not accounting for switching to charging: TODO account for switching to charging.
#Also not accounting for recently seen friendly squares, only squares actively seen right now. TODO change this.
def get_nodes_for_one_enemy(instance, enemy_bot):
    if enemy_bot.seenlast == 0.0:
        return set(regressions2.get_node_index(instance, enemy_bot.position))
    else:
        #Calculate all possible squares the enemy_bot could have reached in the elapsed time.
        enemy_speed = get_enemy_bot_speed(instance, enemy_bot)
        candidates = calculate_nodes_in_range(instance, enemy_bot.position, enemy_bot.seenlast, enemy_speed)
        #Refresh the graph's knowledge of which squares your bots can see.
        update_friendly_sight(instance)
        #Remove candidate notes that we can already see
        candidates = remove_sighted_squares(instance, candidates)       
        return candidates
            
def get_enemy_bot_speed(instance, enemy_bot):
    #TODO account for changes of orders.
    #0: STATE_UNKNOWN, 1: STATE_IDLE, 2: STATE_DEFENDING, 3: STATE_MOVING, 4: STATE_ATTACKING, 5: STATE_CHARGING, 6: STATE_SHOOTING, 7: TAKING_ORDERS
    #8: HOLDING, 9: DEAD 
    if enemy_bot.state in [3, 5, 0]:
        speed = instance.level.runningSpeed
    elif enemy_bot.state in [4, 6, 8, 7]:
        speed = instance.level.walkingSpeed
    elif enemy_bot.state in [1, 2, 9]:
        speed = 0.0
    else:
        speed  = instance.level.runningSpeed
    return speed

def calculate_nodes_in_range(instance, last_position, time_since, enemy_speed):
    max_distance = time_since * enemy_speed
    #used for inaccesible calculations.
    real_max_distance = max_distance
    if max_distance > instance.MAX_ENEMY_DISTANCE:
        max_distance = instance.MAX_ENEMY_DISTANCE  

    if max_distance == 0.0:
        return set([regressions2.get_node_index(instance, last_position)])
    
    #Get bounds for the inital square of nodes to search.
    left_bound = int(max(1, last_position.x - max_distance))
    right_bound = int(min(88, last_position.x + max_distance))
    top_bound = int(min(50, last_position.y + max_distance))
    lower_bound = int(max(1, last_position.y - max_distance))            
    
    #Find nodes in initial square, and prune those that are out of range. (The square's corners.)
    possible_nodes = set()
    for x in range(left_bound, right_bound):
        for y in range(lower_bound, top_bound):
            distance_vector = Vector2(x, y) - last_position 
            if distance_vector.length() > max_distance:
                continue
            elif instance.level.blockHeights[int(x)][int(y)] > 0:
                continue
            node_index = regressions2.get_node_index(instance, Vector2(x, y))
            possible_nodes.add(node_index)
            
    if len(possible_nodes) == 0.0:
        return set([regressions2.get_node_index(instance, last_position)])
                   
    return possible_nodes
    
def update_friendly_sight(instance):
    #Turn all cells currently seen by team to friendly_sight = True in graph.
    for bot in instance.game.team.members:
        if bot.health > 0.0:
            nodes = regressions2.one_bot_sees(instance, bot)
            for node_index in nodes:
                instance.graph.node[node_index]["friendly_sight"] = True

def remove_sighted_squares(instance, candidates):
    #We can't change the size of the set during iteration.
    remove_list = []
    for node in candidates:      
        if instance.graph.node[node]["friendly_sight"] == True:
            remove_list.append(node)
    for node in remove_list:
        candidates.discard(node)
    return candidates


##############################################################################################################
#                          Calculate the Probability That the Enemy Occupies Each of Those                   #
##############################################################################################################

#last_position is explicitly provided because the native last position does not account for spawning or unknown bots.
def set_probability_density(instance, nodes, last_position, enemy_bot, bot_extraps):
    
    #Sets probability of a bot being in each square it possible could reside in.
    total_probability = 0.0
    prob_node_list = []
    #Get initial calculation of bots probability. Scale of numbers is irrelevant, only relative magnitude.
    for node_index in nodes:
        probability = get_probability(instance, node_index, last_position, enemy_bot, bot_extraps)
        total_probability += probability
        prob_node_list.append([node_index, probability])
        
    test_prob = 0.0
    for pair in prob_node_list:
        node_index = pair[0]
        p_enemy = pair[1]

        #Normalize probability distribution for bot's possible squares to 1.0 total.
        p_enemy = p_enemy/total_probability
        test_prob += p_enemy

        #Update graph with new probability.
        if instance.graph.node[node_index]["p_enemy"] == 0.0:
            instance.graph.node[node_index]["p_enemy"] = p_enemy
        else:
            p_not_prior_bots = 1.0 - instance.graph.node[node_index]["p_enemy"]
            p_not_current_bot = 1.0 - p_enemy
            p_neither = p_not_prior_bots * p_not_current_bot
            final_prob_enemy = 1.0 - p_neither
            instance.graph.node[node_index]["p_enemy"] = final_prob_enemy
    #TODO, bug: why is test_prob sometimes 0? print test_prob
   
def get_probability(instance, node, last_position, enemy_bot, bot_extraps):
    #Calculates probability of a given bot being in a possible square it could occupy.
    #Prob based on center
    node_position = regressions2.get_node_vector(instance, node)
    #If we don't have a linear extrap on the enemy, calc random outward radiating ring.
    if enemy_bot not in bot_extraps.keys():
        distance_vector = enemy_bot.position - node_position
        probability = distance_vector.length()**2.0
    else:
        probability = 1.0/(node_position.distance(bot_extraps[enemy_bot])**2.0+1)
    #Prob based on simple linear extrapolation of path
    return probability

def extrapolate(instance):
    points = []
    bot_extraps = {}
    for enemy_bot in instance.enemies.keys():
        if enemy_bot.health > 0.0:
            #Get enemy heading.
            extrapolation = enemy_bot.position - instance.enemies[enemy_bot]
            #If we have no new data on enemy location, assume they are heading in direction of flag.
            #TODO account for pin bots, hunt bots, and defend bots.
            #TODO account for probable pathing... pheremone?
            if extrapolation.length() == 0.0:
                extrapolation = instance.game.team.flag.position - enemy_bot.position
            if extrapolation.length() == 0.0:
                extrapolation = instance.game.enemyTeam.flagScoreLocation - enemy_bot.position          
            extrapolation.normalize()
            #Calculate point enemy should have ran to. TODO make realistic with level speed.
            #TODO use visualizer to simultaneously show with visualization via circle drawings.
            enemy_speed = get_enemy_bot_speed(instance, enemy_bot)*.8 #.8 because not straight running lines.

            #Resolve points going off map by having the bot calculated as at map edge.
            if extrapolation.x > enemy_bot.position.x:
                x_bound = 87
            else:
                x_bound = 2
            if extrapolation.y > enemy_bot.position.y:
                y_bound = 49
            else:
                y_bound = 2

            if enemy_bot.seenlast != None:
                extrapolated_change = extrapolation * enemy_speed * (enemy_bot.seenlast + 1.5)
            else:
                extrapolated_change = extrapolation * enemy_speed * 1.5
                
            if extrapolated_change.x > abs(enemy_bot.position.x - x_bound):
                extrapolated_change.x = x_bound
            if extrapolated_change.y > abs(enemy_bot.position.y - y_bound):
                extrapolated_change.y = y_bound
            
            final_position = enemy_bot.position + extrapolated_change
            x, y = regressions2.sanitize_position(instance, final_position)
            
            final_position = Vector2(x, y)

            node_index = regressions2.get_node_index(instance, final_position)

            vector = regressions2.get_node_vector(instance, node_index)

            points.append(vector)
            bot_extraps[enemy_bot] = vector
            
    if instance.DRAW_POINTS == "extrap":
        instance.points = points
        
    return bot_extraps
                
def store_enemy_positions(instance):
    instance.enemies = {}
    for bot in instance.game.enemyTeam.members:
        if bot.health > 0.0 and bot.seenlast < 25:
            instance.enemies[bot] = bot.position


##############################################################################################################
#                          Calculate the Probability distribution of the Enemies' Cone of Fire               #
##############################################################################################################

def set_fs_density(instance, nodes, enemy_bot):
    node_count = 0
    #Limiting number on how many nodes can be evaluated.
    nodes = get_n_best(instance, nodes)
    
    for node_index in nodes:
        #We don't have the processing power to do this for all nodes, so we'll only do it for likely ones.
        #Basically this takes the best guess about the enemy's facing direction, and assigns the probability based on that
        #that at least one enemy can fire at each node, and at least one can see each node.
        if instance.graph.node[node_index]["p_enemy"] > instance.MINIMUM_ENEMY_PROB:
            assign_single_node_fs_density(instance, node_index, enemy_bot)
            node_count += 1

def get_n_best(instance, nodes):
    #Sort the nodes by the prob density of enemy presence, return predefined n highest.
    prob_list = []
    node_list_length = len(nodes)
    for node_index in nodes:
        p_enemy = instance.graph.node[node_index]["p_enemy"]
        prob_list.append( (p_enemy, node_index) )
        prob_list.sort()
    if node_list_length > instance.TOTAL_FS_NODES:
        prob_list = prob_list[node_list_length - instance.TOTAL_FS_NODES-1:-1]
    return_list = []
    for item in prob_list:
        node_index = item[1]
        return_list.append(node_index)
    return return_list      
    

def assign_single_node_fs_density(instance, source_node_id, enemy_bot):
    bot_position = regressions2.get_node_vector(instance, source_node_id)
    direction = get_direction(instance, enemy_bot)
    #If the bot is definitely dead.
    if enemy_bot.health == 0:
        return
    
    #Get all nodes visible to the hypothetical enemy bot, assign scores to them based on enemy sight and enemy firing capability.
    simulated_bot = {"position": bot_position, "direction" : direction}
    visible_nodes = regressions2.one_bot_sees(instance, enemy_bot, simulated_bot)
    for node_index in visible_nodes:
        node_position = regressions2.get_node_vector(instance, node_index)
        #We care if about what probability the enemy is at the source node being evaluated.
        p_enemy = instance.graph.node[source_node_id]["p_enemy"]
        p_sight = instance.graph.node[node_index]["p_enemy_sight"]
        p_fire = instance.graph.node[node_index]["p_enemy_fire"]
        #We purposefully overestimate their shooting range to have bots play cautiously.
        #We are also estimating at time of, which leaves lots of time for commands, hence the cone is not accurate.
        if (node_position - bot_position).length() < instance.level.firingDistance + 1:
            if p_fire == 0.0:
                instance.graph.node[node_index]["p_enemy_fire"] = p_enemy
            else:
                p_not_prior_fire = 1.0 - p_fire
                p_not_current_fire = 1.0 - p_enemy
                p_neither = p_not_prior_fire * p_not_current_fire
                final_prob_fire = 1.0 - p_neither
                instance.graph.node[node_index]["p_enemy_fire"] = final_prob_fire
                
        if p_sight == 0.0:
            instance.graph.node[node_index]["p_enemy_sight"] = p_enemy
        else:
            p_not_prior_sight = 1.0 - p_sight
            p_not_current_sight = 1.0 - p_enemy
            p_neither = p_not_prior_sight * p_not_current_sight
            final_prob_sight = 1.0 - p_neither
            instance.graph.node[node_index]["p_enemy_sight"] = final_prob_sight
    

def get_direction(instance, enemy_bot):
    #TODO have this account for potentially changing directions.
    if enemy_bot.health == 0:
            return None
    #If the enemy bot is alive, use its last known orientation to figure out where it is aiming.
    else:
        direction = enemy_bot.facingDirection
    return direction
