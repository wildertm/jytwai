import math, itertools, random
from api import vector2, Vector2, commands
#Third party modules
import networkx as nx
#KILLZONE modules
import visibility
#Twilder
import enemy_belief
import spawn_camp

#################################################################################################
#                                        FEATURES                                               #
#################################################################################################

def friendly_to_enemy_ratio(instance, bot, command):
    return (float(len(instance.game.bots_alive))+1.0)/(get_living_enemies(instance)+1.0)

def evaluate_camp_command(instance, bot, command):
    node = get_node_index(instance, bot.position)
    camp_power = instance.graph.node[node]["camp_location"]
    command.description = "%d" % camp_power  
    return camp_power/4.0

def lower_redundant_camp_value(instance, bot, command):
    redundancy = 0
    friendlies = get_friendlies_in_range(instance, bot.position, 4)
    for friendly in friendlies:
        if friendly.state == 0:
            redundancy += 1
    return -float(redundancy)

def go_to_camp(instance, bot, command):
    destination = command.target[-1]
    average_distance = 0.0
    for node in instance.choke_dict.keys():
        position = get_node_vector(instance, node)
        average_distance += destination.distance(position)/len(instance.choke_dict.keys())
    enemies = get_living_enemies(instance)
    return 1000.0/(average_distance+1) * (len(instance.game.bots_alive)+15)/(enemies*4+1.0)

def max_angles(instance, bot, command):
    destination = command.target[-1]
    total_angle = 0.0
    bot_count = 0.0
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.health > 0:
            bot_count += 1
            vector_a = enemy_bot.facingDirection
            vector_b = bot.position - enemy_bot.position
            angle = get_angle(vector_a, vector_b)
            total_angle += angle
    return total_angle/(bot_count+1.0)

def distance(instance, bot, command):
    return (bot.position - command.target[-1]).length()/100

def go_to_flank_brink(instance, bot, command):
    position = command.target[-1]
    goto = 0.0
    minimum_distances = [position.distance(enemy_bot.position) for enemy_bot in instance.game.enemyTeam.members if enemy_bot.health > 0.0]
    minimum_distances.sort()
    if int(len(minimum_distances)/3.0) > 0.0:
        average_minimum_distance = sum(x for x in minimum_distances[0: int(len(minimum_distances)/3.0) ]) / int(len(minimum_distances)/3.0)
    else:
        return 0
    
    #Only do this when we are outside of the brink already.
    if average_minimum_distance > instance.level.firingDistance-6:
        dist_from_flank_range = abs((instance.level.firingDistance) - average_minimum_distance)
        if dist_from_flank_range > 0:
           goto = 100.0/(dist_from_flank_range**1.5+2)
    else:
        goto = 0.0
    return goto/20

def spread_targets2(instance, bot, command):
    redundancy = 0.0
    for friendly in instance.game.team.members:
        if friendly.health > 0:
            friendly_command = instance.bots[friendly.name]["command"]
            if friendly_command != None:
                if type(friendly_command) == commands.Defend:
                    friendly_position = instance.get_bot_from_command(friendly_command).position
                    distance = command.target[-1].distance(friendly_position)
                else:
                    distance = command.target[-1].distance(friendly_command.target[-1])
                if distance < 6:
                    redundancy += 1
    uniqueness = redundancy*5.0
    return -uniqueness


def time_to_score(instance, bot, command):
    if bot.flag != None:
        destination = instance.game.team.flagScoreLocation
        distance_vector = command.target[-1] - destination
        return -distance_vector.length()
    else:
        return 0

def go_toward_flag(instance, bot, command):
    living_enemies = get_living_enemies(instance)
    attractive = 5/(command.target[-1].distance(instance.game.enemyTeam.flag.position)+1)
    return attractive*3

def camp_strategy_go_toward_flag(instance, bot, command):
    their_flag = instance.game.enemyTeam.flag.position
    flag_runners = 0
    closer_bots = 0
    bot_distance = bot.position.distance(their_flag)
    for friendly in instance.game.bots_alive:
        if friendly != bot:
            if friendly.flag:
                print "We already have it. Leave the defense static."
                return 0.0
            f_command = instance.bots[friendly.name]["command"]
            if f_command != None and type(f_command) != commands.Defend:
                target_distance = f_command.target[-1].distance(their_flag)
                distance = friendly.position.distance(their_flag)
                if target_distance < 6.0:
                    flag_runners += 1
                if distance < bot_distance:
                    closer_bots += 1 

    if type(command) == commands.Defend:
        return 0.0
   
    ratio = len(instance.game.bots_alive) / (get_living_enemies(instance)+1)
    if not bot.flag:
        if flag_runners < 2 and closer_bots < 2 and ratio > 1.5 and command.target[-1].distance(their_flag) < 6.0:
            print "GO TO FLAG"
            return 12000.0
        else:
            return 0.0
    else:
        return 0.0
        

def enemy_distance(instance, bot, command):
    total_distance = 0.0
    count = 0.0
    for node_index in instance.graph.nodes():
        p_enemy = instance.graph.node[node_index]["p_enemy"]
        if p_enemy != 0.0:
            node_vector = get_node_vector(instance, node_index)
            total_distance += node_vector.distance(bot.position) * p_enemy
            count += p_enemy
    weighted_average_distance = total_distance/(count+1)

    if type(command) == commands.Attack:
        value = (45 - weighted_average_distance)/3
    elif type(command) == commands.Charge:
        value = (weighted_average_distance - 45)/3
    return value

def enemy_shoots(instance, bot, command):
    total_risk = 0.0
    count = 0.0
    for node_index in instance.graph.nodes():
        p_enemy_fire = instance.graph.node[node_index]["p_enemy_fire"]
        if p_enemy_fire != 0.0:
            total_risk += p_enemy_fire
    return total_risk

#################################################################################################
#                               GRAPH UPDATE FUNCTIONS - BY TWILDER                             #
#################################################################################################

#DEFAULT EDGE WEIGHT IS 5!

def update_score_graph(instance):
    reset_graph(instance)
    #Updates node information about enemy position, sight, fire
    enemy_belief.update_enemy_graph(instance)
    #Updates graph edges to account for new node information
    update_fire_graph(instance, importance = 70.0)
    update_sight_graph(instance, importance = 0.0)
    update_position_graph(instance, importance = 15.0)

#Entry point for all of the graph analysis. Called by the commander.
def update_graph(instance):
    reset_graph(instance)
    #Updates node information about enemy position, sight, fire
    enemy_belief.update_enemy_graph(instance)
    #Updates graph edges to account for new node information
    update_fire_graph(instance, importance = 50)
    update_sight_graph(instance, importance = 1)
    update_position_graph(instance, importance = -2.0)
    update_pheremone_graph(instance, importance = 10)
    spawn_camp.update_choke_redundancy(instance)
                    
def update_fire_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be able to shoot.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy"] + instance.graph.node[end]["p_enemy_fire"]
        current_density = instance.graph.edge[edge[0]][edge[1]]["weight"]
        if current_density + total_density * importance > 0:
            instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance

def update_sight_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be able to see.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy"] + instance.graph.node[end]["p_enemy_sight"]
        current_density = instance.graph.edge[edge[0]][edge[1]]["weight"]
        if current_density + total_density * importance > 0:
            instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance
                    
def update_position_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy"] + instance.graph.node[end]["p_enemy"]
        current_density = instance.graph.edge[edge[0]][edge[1]]["weight"]
        if current_density + total_density * importance > 0:
            instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance
            
def update_pheremone_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["pheremone"] + instance.graph.node[end]["pheremone"]
        current_density = instance.graph.edge[edge[0]][edge[1]]["weight"]
        if current_density + total_density * importance > 0:
            instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance

def update_choke_graph(instance):
    #Weights edges based on where the enemy is likely to be.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["choke_covered"] + instance.graph.node[end]["choke_covered"]
        current_density = instance.graph.edge[edge[0]][edge[1]]["choke_covered"]
        instance.graph.edge[edge[0]][edge[1]]["choke_covered"] += total_density
        
def reset_graph(instance):
    """0s probability of enemy being at each node."""
    for node_index in instance.graph.nodes():
        instance.graph.node[node_index]["p_enemy"] = 0.0
        instance.graph.node[node_index]["friendly_sight"] = False
        instance.graph.node[node_index]["p_enemy_fire"] = 0.0
        instance.graph.node[node_index]["p_enemy_sight"] = 0.0
        instance.graph.node[node_index]["weight"] = 0.0
        if instance.counter % instance.COMMAND_RATE == 0.0 or instance.counter == 1:
            instance.graph.node[node_index]["pheremone"] = 0.0
        
    for edge in instance.graph.edges():
        start = edge[0]
        end = edge[1]
        instance.graph.edge[edge[0]][edge[1]]["choke_covered"] = 0.0
        instance.graph.edge[start][end]["weight"] = 5.0

    for bot_name in instance.bots:
        instance.bots[bot_name]["visibility"] = set()
    for key in instance.choke_dict.keys():
        instance.choke_dict[key]["redundancy"] = 0.0
            

#################################################################################################
#                                    UTILITY FUNCTIONS                                          #
#################################################################################################

def get_friendlies_in_range(instance, position, min_range):
    friendlies = []
    for friendly in instance.game.team.members:
        if friendly.health > 0 and friendly.position.distance(position) < min_range:
            friendlies.append(friendly)
    return friendlies

def get_living_enemies(instance):
    #Doesn't account for recently spawned. That's fine.
    livers = 0
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.health > 0:
            livers += 1
    return livers
            

def calculate_total_enemy_density(instance, nodes):
    total_density = 0.0
    for node_index in nodes:
        total_density += instance.graph.node[node_index]["p_enemy"]
    return total_density

def get_continue_command(instance, bot, command):
    current_x = bot.position.x
    current_y = bot.position.y
    if type(command) != commands.Defend:
        current_waypoint_index = None
        #Find roughly where we are in the bot's trajectory.
        for waypoint in command.target:          
            total_error = waypoint.x - current_x + waypoint.y - current_y
            if abs(total_error) < 1.0: #TODO tweak to pick best of two closest nodes, this always picks the first and so thinks bots are farther away than they are.
                current_waypoint_index = command.target.index(waypoint)
                break
        #deals with now waypoints in path being within 1 of target.
        if current_waypoint_index == None:
            for waypoint in command.target:          
                total_error = waypoint.x - current_x + waypoint.y - current_y
                if abs(total_error) < 4.0:
                    current_waypoint_index = command.target.index(waypoint)
                    break        
        #The rest of the bot's trajectory on the current plan
        future_waypoints = command.target[current_waypoint_index:]
            
        if type(command) == commands.Attack:
            continue_command = type(command)(bot.name, future_waypoints, lookAt = command.lookAt, description = command.description)    
        if type(command) == commands.Charge:
            continue_command = type(command)(bot.name, future_waypoints, description = command.description)
            
    if type(command) == commands.Defend:
        #For defend we don't need to reconstruct future path. The bot hasn't gone anywhere!
        return command
    return continue_command
    

def evaluate_continue_present_command(instance, bot, command):
    command = get_continue_command(instance, bot, command)
    value = instance.get_hueristic_value(bot, command)
    value += 2 #TODO figure out better way to calculate value of continuing command.
    return value

def enemy_shoots_square(instance, bot, command):
    destination = command.target[0]
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.seenlast < 5.0 and enemy_bot.health > 0.0:
            if can_bot_shoot(instance, enemy_bot, destination, added_distance = 4):
                return 1
    return 0

def sanitize_position(instance, position):
    #Takes a position we accidentally rounded into that is a block and hence has no node, returns a nearby node that isn't.
    #Since we do this for a lot of points, this is built to only check the height for all but problem points.
    i = int(position.x)
    j = int(position.y)
    
    #Deal with flying off map; I.E. through extrapolation.
    if i > 87.0:
        print "ALTERING X TO BE ON MAP"
        i = 87
    if i < 0.0:
        i = 1
        print "ALTERING X TO BE ON MAP"
    if j < 0.0:
        j = 0
        print "ALTERING Y TO BE ON MAP"
    if j > 49.0:
        j = 49
        print "ALTERING Y TO BE ON MAP"
    
    count = 0
    #If we have been passed a blocked point
    if instance.level.blockHeights[i][j] != 0:
        while instance.level.blockHeights[i][j] != 0:
            count += 1
            if i > 40:
                i = i-1
            else:
                i = i+1
            if j > 25:
                j = j-1
            else:
                j = j+1
            #Assures no infinite loops if somehow caught in a large square at 40, 25.
            if count % 10 == 0:
                count = 0
                if i > 40:
                    i = i-3
                else:
                    i = i+3
                if j > 25:
                    j = j-3
                else:
                    j = j+3
    #Deal with 0 node bug.
    if i == 0 and j == 0:
        i += 10
        j += 10
        i, j = sanitize_position(instance, Vector2(i,j))
    return (i, j)

def get_node_index(instance, position):
    #Ensure we won't accidentally round ourselves into a terrain piece.
    i = position.x
    j = position.y
    if i == 0:
        i = 1
    if j == 0:
        j = 1
    i, j = sanitize_position(instance, Vector2(i,j))

    try:
        width = instance.graph.graph["map_width"]
        #Node bug. #TODO find out real reason for bug instead of hacking solution.
        node_index = i + j*width
        test = instance.graph.node[node_index]
    except:
        print "INDEX BUG"
        print "i = ", i
        print "j = ", j
        print "BLOCK HEIGHT: ", instance.level.blockHeights[i][j]
    return node_index

def get_node_vector(instance, node_index):
    try:
        position = instance.graph.node[node_index]["position"]
    except:
        print "POSITION BUG... OFFENDING INDEX: ", node_index
        print instance.graph.node[node_index]
        position = instance.game.enemyTeam.flag.position
    x = position[0]
    y = position[1]
    return Vector2(x , y)

def get_path(instance, start, destination):
    #Deal with various node bugs.
    start_i, start_j = sanitize_position(instance, start)
    dest_i, dest_j =  sanitize_position(instance, destination)
    start = Vector2(start_i, start_j)
    destination = Vector2(dest_i, dest_j)
    #Get the node index.
    start_node = get_node_index(instance, start)
    destination_node = get_node_index(instance, destination)
    try:
        path = nx.shortest_path(instance.graph, source = start_node, target = destination_node, weight = "weight")
    except:
        print "PATHING BUG, TARGET INDEX ERROR"
        path = nx.shortest_path(instance.graph, source = start_node, target = get_node_index(instance, instance.game.enemyTeam.flag.position), weight = "weight")
    #Convert list of node indexes to list of vectors for those nodes.
    for path_index in range(len(path)):
        node_index = path[path_index]
        node_vector = get_node_vector(instance, node_index)
        path[path_index] = node_vector
    return path
                    
def can_bot_see(instance, bot, position):
    position_to_bot_vector = position - bot.position
    if position == bot.position:
        return True
    angle = get_angle(bot.facingDirection, position_to_bot_vector)
    bot_fov = instance.level.fieldOfViewAngles[bot.state]
    if abs(angle) < bot_fov/2.0:
        return True
    else:
        return False

def can_bot_shoot(instance, bot, position, added_distance = 0):
    destination_to_bot = bot.position - position
    if can_bot_see(instance, bot, position) and destination_to_bot.length() < instance.level.firingDistance + added_distance:
        return True
    else:
        return False

def get_angle(vector_a, vector_b):
    try:
        value_to_use = vector_a.dotProduct(vector_b)/abs((vector_a.length() * vector_b.length()))
        #Deal with bit expression problems and inverse cos domain.
        if value_to_use <= -1:
            value_to_use = -.9999995
        elif value_to_use >= 1:
            value_to_use = .999995
        angle = math.acos(value_to_use)
    except Exception:
        print "GET ANGLE BUG"
        print vector_a
        print vector_b
        print vector_a.length() * vector_b.length()
        print vector_a.dotProduct(vector_b)
        print vector_a.dotProduct(vector_b)/abs((vector_a.length() * vector_b.length()))
        print math.acos(vector_a.dotProduct(vector_b)/abs((vector_a.length() * vector_b.length())))
    return angle
        
def getNodeIndex(instance, position):
    i = int(position.x)
    j = int(position.y)
    width = instance.graph.graph["map_width"]
    return i+j*width

def one_bot_visibility(instance, bot):
        position = bot.position
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x, y)))
        w.compute(position)
        instance.bots[bot.name]["visibility"] = set([get_node_index(instance, Vector2(x, y)) for x, y in cells])
        return cells

def one_bot_sees(instance, bot, simulated_bot = None):
    nodes = []
    #finds visible squares to one bot, or a dictionary with keys "direction" and "position" if simulated_bot is specified.
    if not simulated_bot:
        cells = one_bot_visibility(instance, bot)
        for cell in cells:
            x = cell[0]
            y = cell[1]
            #Deals with problem of 1 height blocks being visible but not in path graph.
            if instance.level.blockHeights[x][y] == 1.0:
                continue
            cell_position = Vector2(x, y)
            if can_bot_see(instance, bot, cell_position):
                node_index = get_node_index(instance, cell_position)
                nodes.append(node_index)
    #This is for when we are looking at visibility points along a path as opposed to for a specific bot. The lack of DRY is bad,
    #but not backbreaking. #TODO refactor when free time allows.
    else:
        position = simulated_bot["position"]
        direction = simulated_bot["direction"]
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x, y)))
        w.compute(position)
        for cell in cells:
            x = cell[0]
            y = cell[1]
            #Deals with problem of 1 height blocks being visible but not in path graph.
            if instance.level.blockHeights[x][y] == 1.0:
                continue
            cell_position = Vector2(x, y)
            position_to_bot_vector = cell_position - position
            angle = get_angle(direction, position_to_bot_vector)
            bot_fov = instance.level.fieldOfViewAngles[bot.state]
            if not bot_fov:
                bot_fov = 1.57
            if abs(angle) < bot_fov/2.0:
                node_index = get_node_index(instance, cell_position)
                nodes.append(node_index)
    return nodes

def make_graph(instance):
        blocks = instance.level.blockHeights
        width, height = len(blocks), len(blocks[0])

        g = nx.Graph(directed=False, map_height = height, map_width = width)

        #Makes graph with nodes of all "blocks" in level
        instance.terrain = []
        for j in range(0, height):
            row = []
            for i in range(0, width):
                if blocks[i][j] == 0:
                    g.add_node(i+j*width, position = (float(i)+0.5, float(j)+0.5), weight = 0.0)
                    row.append(i+j*width)
                else:
                    row.append(None)
            instance.terrain.append(row)
            
        #Add edges for each possible adjacent combination
        for i, j in itertools.product(range(0, width), range(0, height)):
            p = instance.terrain[j][i]
            if not p: continue
    
            if i < width-1:
                q = instance.terrain[j][i+1]
                if q:
                    e = g.add_edge(p, q, weight = 1.0)    
            if j < height-1:
                r = instance.terrain[j+1][i]
                if r:
                    e = g.add_edge(p, r, weight = 1.0)
                    
        #Fixes bug where many things had no path to node 0.
        try:
            neighbors = g.neighbors(0)
            for neigbor in neighbors:
                g.remove_edge(0, neighbor)
            g.remove_node(0)
        except:
            print "NEIGHBORS BUG"
            
        #Sets final graph as attribute to the Commander instance.
        instance.graph = g


#################################################################################################
#           GRAPHICS LOGIC - ALL CODE HERE BY KILLZONE - MILDLY REFACTORED BY TWILDER         ###
#################################################################################################

def initialize_graphics(instance):
    from PySide import QtGui, QtCore
    from visualizer import VisualizerApplication

    #Calculates points to be visualized, stores as "ambushes" which are visualized.        
    def calculatePOIS(points = []):        
        results = points
        if points == None:
            for x in range(2):
                p = instance.level.findRandomFreePositionInBox(instance.level.area)
                o = Vector2(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5)).normalized()
                results.append(p)
        instance.ambushes = []
        instance.ambushes = results  
    calculatePOIS()
    
    def drawPreWorld(visualizer):
        brightest = max([instance.visibilities.pixel(i,j) for i, j in itertools.product(range(88), range(50))])

        for i, j in itertools.product(range(88), range(50)):            
            n = instance.terrain[j][i]
            if n:
                if instance.mode == instance.MODE_VISIBILITY:
                    d = instance.visibilities.pixel(i,j) * 255 / (brightest+1)
            else:                
                d = 32
            visualizer.drawPixel((i, j), QtGui.qRgb(d,d,d))
                
    def drawPreBots(visualizer):
        for p in instance.ambushes:
            visualizer.drawCircle(p, QtGui.qRgb(255 ,255 ,0), 5)
            
    def keyPressed(e):
        if e.key() == QtCore.Qt.Key_Space:
            instance.mode = 1 - instance.mode

    #Main logic #!!!! REQUIRES INSTANCE TO HAVE GRAPH
    instance.mode = instance.MODE_VISIBILITY
    instance.visualizer = VisualizerApplication(instance)

    instance.visualizer.setDrawHookPreWorld(drawPreWorld)
    instance.visualizer.setDrawHookPreBots(drawPreBots)
    instance.visualizer.setKeyboardHook(keyPressed)

    #Coloration based on score in an 88 by 50 pixel grid?
    #Grid squares are set with setPixel(xcoord, ycoord, intRepresentingDarkness)
    instance.visibilities = QtGui.QImage(88, 50, QtGui.QImage.Format_ARGB32)
    instance.visibilities.fill(0)

    def evaluate(position, orientation, callback):
        return 1      

#################################################################################################
#        GRAPHICS UPDATES - HANDLES UPDATING VISUALS FOR VARIOUS FACTORS - BY TWILDER         ###
#################################################################################################

def update_graphics_friendly_sight(instance):  
    instance.visibilities.fill(0)
    for node in instance.graph.nodes():
        if instance.graph.node[node]["friendly_sight"]:
            x = instance.graph.node[node]["position"][0]
            y = instance.graph.node[node]["position"][1]
            instance.visibilities.setPixel(x, y, 1.0)

#Update graphics based on one of the probabilities on our enemy graph.
def update_graphics_probability(instance, mode = "p_enemy"):
    if not instance.DRAW_POINTS:
        #Don't wipe the etch-a-sketch for ambush. We only calc it once - at the start.
        if instance.GRAPHICS not in ["ambush", "exit_path", "camp_target", "camp_location"]:
            instance.visibilities.fill(0)
        for node in instance.graph.nodes():
            try:
                x = instance.graph.node[node]["position"][0]
                y = instance.graph.node[node]["position"][1]
                p_mode_true = instance.graph.node[node][mode]
                if instance.GRAPHICS in ["ambush", "exit_path", "camp_target", "camp_location", "choke_covered"]:
                    instance.visibilities.setPixel(x, y, p_mode_true)
                else:
                    instance.visibilities.setPixel(x, y, p_mode_true * 254)
            except:
                pass

def draw_points(instance, points):
    #Pass a list of positions, this draws them
    #For visualizing positions
    if instance.DRAW_POINTS:
        for position in points:
            x = position.x
            y = position.y
            instance.visibilities.setPixel(x, y, 255)

#################################################################################################
#        Irrelevant code snippets, fallen by the wayside - BY TWILDER                         ###
#################################################################################################

#Replaceed by automatic path selection                                
def enemy_shoots_path(instance, bot, command):
    #Use graph to calculate if any enemies can shoot any square in selected path.
    for waypoint in command.target:
        node_index = get_node_index(instance, waypoint)
        if instance.graph.node[node_index]["weight"] == 1.0:
            return 1
    else:
        return 0

#Replaceed by automatic look selection
def look_toward_enemies(instance, bot, command):
    points = len(command.target)
    relevant_waypoints = [bot.position]
    relevant_waypoints += command.target[0:1]

    total_enemy_density = 0.0
    for waypoint in relevant_waypoints:
        if type(command) == commands.Attack:
            direction = command.lookAt
        elif type(command) == commands.Defend:
            direction = bot.position + command.facingDirection
        sim_bot = {"position": waypoint , "direction": direction}
        nodes = one_bot_sees(instance, bot, simulated_bot = sim_bot)

        total_enemy_density += calculate_total_enemy_density(instance, nodes)

    return total_enemy_density


def improve_camp_command(instance, bot, command):
    value = 0
    if bot.state == 0:
        current_value = int(instance.bots[bot.name]["command"].description)
        current_node = get_node_index(instance, bot.position)
        move_to = set()
        move_to.add(current_node)
        for x in range(4):
            neighbors = set()
            for node in move_to:
                neighbors2 = instance.graph.neighbors(node)
                neighbors = neighbors.union(neighbors2)
            move_to = move_to.union(neighbors)
        maximum = current_value
        for node_index in move_to:
            better_value_nearby = instance.graph.node[node_index]["camp_location"]
            if  better_value_nearby > maximum:
                maximum = better_value_nearby
        if maximum > current_value:
            value -= maximum
    return value

def popular_ground(instance, bot, command):
    node_index = get_node_index(instance, command.target[-1])
    visible_score = instance.graph.node[node_index]["ambush"]/20
    return visible_score

def calculate_control_main_route2(instance):        
        #Set ambush dictionary.
        for node_index in instance.graph.nodes():
            instance.graph.node[node_index]["ambush"] = 0.0

        start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
        instance.graph.add_node("enemy_base", position = (start.x, start.y), weight = 0.0)
        instance.graph.node["enemy_base"]["ambush"] = 0.0
            
        for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
            instance.graph.add_edge("enemy_base", instance.terrain[j][i], weight = 1.0)                       

        our_flag_node = get_node_index(instance, instance.game.team.flag.position)
        enemy_score_node = get_node_index(instance, instance.game.enemyTeam.flagScoreLocation)
        enemy_flag_node = None
        
        vb2f = nx.shortest_path(instance.graph, source="enemy_base", target=our_flag_node)
        vf2s = nx.shortest_path(instance.graph, source=our_flag_node, target=enemy_score_node)
        
        path = vb2f + vf2s
        edgesinpath=zip(path[0:],path[1:])        
        for vt, vf in edgesinpath[:-1]:
            if "position" not in instance.graph.node[vf]:
                continue
            position = Vector2(*instance.graph.node[vf]["position"])
            if "position" not in instance.graph.node[vt]:
                continue
            next_position = Vector2(*instance.graph.node[vt]["position"])
            if position == next_position:
                continue
            orientation = (next_position - position).normalized()

            def visible(p):
                delta = (p-position)
                l = delta.length()
                if l < instance.level.firingDistance:
                    return True
                else:
                    return False

            cells = []
            w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x,y)))
            w.compute(position)

            for x, y in [c for c in cells if visible(Vector2(c[0]+0.5, c[1]+0.5))]:
                instance.graph.node[get_node_index(instance, Vector2(x,y))]["ambush"] += 2.0
