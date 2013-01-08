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
    regressions2.reset_graph(instance)
    known_enemies = get_known_enemies(instance)
    at_large_enemies = get_at_large_enemies(instance, known_enemies)
    #Find last known whereabouts and condition of each enemy bots
    at_large_enemies = account_for_spawns(instance, at_large_enemies)

    
    #Account for at large enemies list complete with last seen positions and times of all unseen enemies.
    bot_nodes_list = [] # Stores info on which bot accounted for which nodes.
    for enemy_bot_info in at_large_enemies:
        enemy_bot = enemy_bot_info[0]
        last_position = enemy_bot_info[1]
        time_of_position = enemy_bot_info[2]
        #Skip if the information is very stale.
        if instance.game.match.timePassed - time_of_position > 20.0:
            print "SKIPPING DATA THAT IS OUTDATED ON BOT %s" % enemy_bot.name
            continue
        #Based on these variables, calculate nodes that the bot could occupy.
        nodes = get_nodes_for_one_enemy(instance, enemy_bot, last_position, time_of_position)        
        set_probability_density(instance, nodes, last_position, enemy_bot)
        
        bot_nodes_list.append((enemy_bot, nodes))

    #Account for position and probability of all definitively known enemies.
    known_enemy_nodes = set()
    for enemy_bot in known_enemies:
        node_index = regressions2.get_node_index(instance, enemy_bot.position)
        known_enemy_nodes.add(node_index)
        instance.graph.node[node_index]["friendly_sight"] = True
        instance.graph.node[node_index]["p_enemy"] = 1.0
        nodes = [node_index]

        bot_nodes_list.append((enemy_bot, nodes))

    #Set sight and cone of fire data based on all nodes enemy_bots could be present in.
    #TODO - counts double for overlap squares...
    for enemy_bot, nodes in bot_nodes_list:
        set_fs_density(instance, nodes, enemy_bot)   

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
                position = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
            else:
                time_seen = instance.game.match.timePassed - enemy_bot.seenlast
                position = enemy_bot.position
            unknown_enemies.append([enemy_bot, position, time_seen])
    return unknown_enemies

def account_for_spawns(instance, at_large_enemies):
    #Updates positions of enemies whose health is ostensibly 0 based on if they have respawned.
    #Dead enemies that have respawned still appear as health 0, and are very much a threat!
    for enemy_info in at_large_enemies:
        if enemy_info[0].health == 0 or None:
            #See if bot has respawned since it was killed.
            respawned_time = get_respawn(instance, enemy_info[0])
            #If the bot respawned figure count its last seen as the center of its respawn.
            if respawned_time != None:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = instance.game.match.timePassed - respawned_time + .5
            #If the bot is respawning in the next two seconds, count its last seen as the center of its respawn.
            elif instance.game.match.timeToNextRespawn < 2.00:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = 2.0
            #If the game has just begun and the bot is chilling in his spawn, assign him as there. #TODO better spawn positioning.
            elif enemy_info[0].state == 0:
                enemy_spawn_coord = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
                enemy_info[1] = enemy_spawn_coord
                enemy_info[2] = -1.5 #This is a hack so that we evaluate enemy bots as present at the start. It works pretty well.
            #If none of the above are true, the bot is dead and we don't need to worry about him.
            else:
                at_large_enemies.remove(enemy_info)
##    print at_large_enemies
    return at_large_enemies
    
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
#                          Calculate the Squares a Given Enemy Could possible Occupy                         #
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
    if max_distance > 55:
        max_distance = 55  

    #Get bounds for the inital square of nodes to search.
    left_bound = int(max(1, last_position.x - max_distance))
    right_bound = int(min(88, last_position.x + max_distance))
    top_bound = int(min(50, last_position.y + max_distance))
    lower_bound = int(max(1, last_position.y - max_distance))

##    print "enemy_speed: ", enemy_speed
##    print "time_since: ", time_since
##    print "left_bound: ", left_bound 
##    print "right_bound: " , right_bound 
##    print "top_bound: ", top_bound 
##    print "lower_bound: ", lower_bound
    
    
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
    return possible_nodes
    
def update_friendly_sight(instance):
    #Turn all cells currently seen by team to friendly_sight = True in graph.
    for bot in instance.game.team.members:
        if bot.health > 0:
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
def set_probability_density(instance, nodes, last_position, enemy_bot):
    #Sets probability of a bot being in each square it possible could reside in.
    total_probability = 0.0
    prob_node_list = []
    #Get initial calculation of bots probability. Scale of numbers is irrelevant, only relative magnitude.
    for node_index in nodes:
        probability = get_probability(instance, node_index, last_position, enemy_bot)
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
        

def get_probability(instance, node, last_position, enemy_bot):
    #Calculates probability of a given bot being in a possible square it could occupy.

    #Prob based on center
    enemy_position = last_position
    node_position = regressions2.get_node_vector(instance, node)
    distance_vector = enemy_position - node_position
    probability = distance_vector.length()**2
    #Prob based on simple linear extrapolation of path
    return probability

##############################################################################################################
#                          Calculate the Probability distribution of the Enemies' Cone of Fire               #
##############################################################################################################

def set_fs_density(instance, nodes, enemy_bot):
    for node_index in nodes:
        #We don't have the processing power to do this for all nodes, so we'll only do it for likely ones.
        #Basically this takes the best guess about the enemy's facing direction, and assigns the probability based on that
        #that at least one enemy can fire at each node, and at least one an see each node.
        if instance.graph.node[node_index]["p_enemy"] > .008:
            assign_single_node_fs_density(instance, node_index, enemy_bot)

def assign_single_node_fs_density(instance, source_node_id, enemy_bot):
    bot_position = regressions2.get_node_vector(instance, source_node_id)
    direction = get_direction(instance, enemy_bot)
    #If the bot is definitely dead (IE hasn't respawned etc...) don't bother filling in data about it.
    #Get direction returns a direction for just starting bots.
    if direction == None:
        return
        
    #Get all nodes visible to the hypothetical enemy bot, assign scores to them based on enemy sight and enemy firing capability.
    simulated_bot = {"position": bot_position, "direction" : direction}
    visible_nodes = regressions2.one_bot_sees(instance, enemy_bot, simulated_bot)
    #TODO
    for node_index in visible_nodes:
        node_position = regressions2.get_node_vector(instance, node_index)
        #We care if about what probability the enemy is at the source node being evaluated.
        p_enemy = instance.graph.node[source_node_id]["p_enemy"]
        p_sight = instance.graph.node[node_index]["p_enemy_sight"]
        p_fire = instance.graph.node[node_index]["p_enemy_fire"]
        #TODO make fn to DRY this. #@FIRING
        #We purposefully overestimate their shooting range to have bots play cautiously.
        #We are also estimating at time of, which leaves lots of time for commands, hence the cone is not accurate.
        if (node_position - bot_position).length() < instance.level.firingDistance + 6:
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
    direction = None
    if enemy_bot.health == 0 or None:
        #See if bot has respawned since it was killed.
        respawned_time = get_respawn(instance, enemy_bot)
        #If the bot respawned, is about to respawn, or has state_unknown, assume it is in its spawn and facing the closest of our bots.
        if respawned_time != None or instance.game.match.timeToNextRespawn < 2.00 or enemy_bot.state == 0:
            spawn_position = Vector2.midPoint(instance.game.enemyTeam.botSpawnArea[0], instance.game.enemyTeam.botSpawnArea[1])
            our_bot_positions = [bot.position for bot in instance.game.team.members]
            closest = float("inf")
            closest_point = None
            for position in our_bot_positions:
                distance = (position - spawn_position).length()
                if distance < closest:
                    closest_point = position
                    closest = distance
            direction = closest_point - spawn_position
        else:
            #Enemy is dead and hasn't respawned, return no probability for look directions.
            return None
        
    #If the enemy bot is alive, use its last known orientation to figure out where it is aiming.
    else:
        direction = enemy_bot.facingDirection
    return direction
