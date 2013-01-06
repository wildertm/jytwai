import math, itertools, random
from api import vector2, Vector2, commands
#Third party modules
import networkx as nx
#KILLZONE modules
import visibility
from visualizer import VisualizerApplication
#From twilder
import regressions2

def update_enemy_graph(instance):
    """Updates each node with probability of enemy presence."""
    reset_enemy_graph(instance)
    known_enemies = get_known_enemies(instance)
    at_large_enemies = get_at_large_enemies(instance, known_enemies)
    #Find last known whereabouts and condition of each enemy bots
    account_for_spawns(instance, at_large_enemies)

    #Accoun for at large enemies list complete with last seen positions and times of all unseen enemies.
    master_nodes = []
    for enemy_bot_info in at_large_enemies:
        enemy_bot = enemy_bot_info[0]
        last_position = enemy_bot_info[1]
        time_of_position = enemy_bot_info[2]
        #Based on these variables, calculate nodes that the bot could occupy.
        nodes = get_nodes_for_one_enemy(instance, enemy_bot, last_position, time_of_position)        
        set_probability_density(instance, nodes, last_position)
##        master_nodes.append(nodes)

    #Account for position and probability of all definitively known enemies.
    known_enemy_nodes = set()
    for enemy_bot in known_enemies:
        node_index = regressions2.get_node_index(instance, enemy_bot.position)
        known_enemy_nodes.add(node_index)
        instance.graph.node[node_index]["friendly_sight"] = True
        instance.graph.node[node_index]["p_enemy"] = 1.0
    master_nodes.append(known_enemy_nodes)

    #Update graphics to show probability distribution of enemies as we assess it.
    regressions2.update_graphics_probability_enemy(instance)

    #Update our graphics to debug enemy belief.
##    regressions2.update_graphics_enemy_belief(instance, master_nodes)
    
    #Update our graphics to debug friendly sight.
##    regressions2.update_graphics_friendly_sight(instance)
    
    
def reset_enemy_graph(instance):
    """0s probability of enemy being at each node."""
    for node_index in instance.graph.nodes():
        instance.graph.node[node_index]["p_enemy"] = 0.0
        instance.graph.node[node_index]["friendly_sight"] = False

##############################################################################################################
#                          Discover Enemy Last Seen Positions Accounting for Spawns                          #
##############################################################################################################

def get_known_enemies(instance):
    #List enemies we have 100% certain location knowledge on.
    known_enemies = []
    for bot in instance.game.team.members:
        for enemy_bot in bot.visibleEnemies:
            if enemy_bot not in known_enemies:
                known_enemies.append(enemy_bot)
    return known_enemies    

def get_at_large_enemies(instance, known_enemies):
    #List enemies without 100% certainty of location.
    #Format is bot, last known position.
    unknown_enemies = []
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot not in known_enemies and enemy_bot not in unknown_enemies:
            if enemy_bot.seenlast == None:
                time_seen = 0.0
            else:
                time_seen = instance.game.match.timePassed - enemy_bot.seenlast
            unknown_enemies.append([enemy_bot, enemy_bot.position, time_seen])
    return unknown_enemies

def account_for_spawns(instance, at_large_enemies):
    #Updates positions of enemies whose health is ostensibly 0 based on if they have respawned.
    #Dead enemies that have respawned still appear as health 0, and are very much a threat!
    for enemy_info in at_large_enemies:
        enemy_bot = enemy_info[0]
        
        if enemy_bot.health == 0:
            #See if bot has respawned since it was killed.
            respawned_time = get_respawn(instance, enemy_bot)
            #If the bot respawned figure count its last seen as the center of its respawn.
            if respawned_time != None:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = instance.game.match.timePassed - respawned_time
            #If the bot is respawning in the next two seconds, count its last seen as the center of its respawn.
            elif instance.game.match.timeToNextRespawn < 2.00:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = 0.0
            #If the game has just begun and the bot is chilling in his spawn, assign him as there. #TODO better spawn positioning.
            elif enemy_bot.state == 0:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = 0.0

def get_respawn(instance, enemy_bot):
    #If the bot has respawned and is not yet seen, we will get to a respawn time before we get to a time it was killed.
    killed_time = None
    respawned_time = None
    for event_index in range(len(instance.game.match.combatEvents)-1, 0):
        if instance.game.match.combatEvents[event_index].subject == enemy_bot:
            if event.type == TYPE_KILLED:
                break
            if event.type == TYPE_RESPAWN:
                respawned_time = event.time
    return respawned_time
            
##############################################################################################################
#                          Calculate the Squares a Given enemy Could possible Occupy                         #
##############################################################################################################

#Initially not accounting for switching to charging: TODO account for switching to charging.
#Also not accounting for recently seen friendly squares, only squares actively seen right now. TODO change this.
def get_nodes_for_one_enemy(instance, enemy_bot, last_position, time_of_position):
    time_since = instance.game.match.timePassed - time_of_position
    #Calculate all possible squares the enemy_bot could have reached in the elapsed time.
    enemy_speed = get_enemy_bot_speed(instance, enemy_bot)
    candidates = calculate_nodes_in_range(instance, last_position, time_since, enemy_speed)
    
    #Refresh the graph's knowledge of which squares your bots can see.
    update_friendly_sight(instance)
    #Remove candidate notes that we can already see
    candidates = remove_sighted_squares(instance, candidates)
    
    return candidates
            
def get_enemy_bot_speed(instance, enemy_bot):
    #TODO account for changes of orders.
    #0: STATE_UNKNOWN, 1: STATE_IDLE, 2: STATE_DEFENDING, 3: STATE_MOVING, 4: STATE_ATTACKING, 5: STATE_CHARGING, 6: STATE_SHOOTING, 7: TAKING_ORDERS
    if enemy_bot.state in [3, 5, 0]:
        speed = instance.level.runningSpeed
    elif enemy_bot.state in [4, 6, 7]:
        speed = instance.level.walkingSpeed
    elif [1, 2]:
        speed = 0.0
    else:
        speed  = instance.level.runningSpeed
    return speed

def calculate_nodes_in_range(instance, last_position, time_since, enemy_speed):
    max_distance = time_since * enemy_speed
    if max_distance > 25:
        max_distance = 25  

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
            #@terrain
            node_index = regressions2.get_node_index(instance, Vector2(x, y))
            possible_nodes.add(node_index)
##    print 'last_position: ', last_position, ' len_nodes: ', len(possible_nodes), " time_since: ", time_since, " max_distance: ", max_distance
    return possible_nodes
    
def update_friendly_sight(instance):
    #Turn all cells currently seen by team to friendly_sight = True in graph.
    for bot in instance.game.team.members:
        if bot.health > 0:
            cells = regressions2.oneBotsVisibility(instance, bot)
            for cell in cells:
                x = cell[0]
                y = cell[1]
                #Deals with problem of 1 height blocks being visible but not in path graph.
                if instance.level.blockHeights[x][y] == 1.0:
                    continue
                cell_position = Vector2(x, y)
                if regressions2.can_bot_see(instance, bot, cell_position):
                    node_index = regressions2.get_node_index(instance, cell_position)
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

def set_probability_density(instance, nodes, last_position):
    #Sets probability of a bot being in each square it possible could reside in.
    total_probability = 0.0
    prob_node_list = []
    #Get initial calculation of bots probability. Scale of numbers is irrelevant, only relative magnitude.
    for node_index in nodes:
        probability = get_probability(instance, node_index, last_position)
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
            p_not_prior_bots = 1 - instance.graph.node[node_index]["p_enemy"]
            p_not_current_bot = 1 - p_enemy
            p_neither = p_not_prior_bots * p_not_current_bot
            final_prob_enemy = 1 - p_neither
            instance.graph.node[node_index]["p_enemy"] = final_prob_enemy
    print 'test_prob: ', test_prob, '            **Should == 1.0'
        

def get_probability(instance, node, last_position):
    #Calculates probability of a given bot being in a possible square it could occupy.
    enemy_position = last_position
    node_position = regressions2.get_node_vector(instance, node)
    distance_vector = enemy_position - node_position
    probability = 1/(distance_vector.length() + 1)**2
    return probability
