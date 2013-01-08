import math, itertools, random
from api import vector2, Vector2, commands
#Third party modules
import networkx as nx
#KILLZONE modules
import visibility
from visualizer import VisualizerApplication
#Twilder
import enemy_belief

#################################################################################################
#                                       GRAPH BASED FEATURES                                    #
#################################################################################################

def time_to_score(instance, bot, command):
    if bot.flag != None:
        destination = instance.game.team.flagScoreLocation
        distance_vector = command.target[-1] - destination
        return distance_vector.length()
    else:
        return 0

def go_toward_flag(instance, bot, command):
    return command.target[-1].distance(instance.game.enemyTeam.flag.position)

def enemy_distance(instance, bot, command):
    total_distance = 0.0
    count = 0.0
    for node_index in instance.graph.nodes():
        p_enemy = instance.graph.node[node_index]["p_enemy"]
        if p_enemy != 0.0:
            node_vector = get_node_vector(instance, node_index)
            total_distance += node_vector.distance(command.target[-1]) * p_enemy
            count += p_enemy
    weighted_average_distance = total_distance/(count+1)

    #Encourage charging when further away.
    if type(command) == commands.Charge:
        if weighted_average_distance > 35:
            weighted_average_distance *= 1.5
    elif type(command) == commands.Attack:
        if weighted_average_distance < 30:
             weighted_average_distance *= 1.5
                 
    return weighted_average_distance

def enemy_shoots_path(instance, bot, command):
    #Use graph to calculate if any enemies can shoot any square in selected path.
    for waypoint in command.target:
        node_index = get_node_index(instance, waypoint)
        if instance.graph.node[node_index]["weight"] == 1.0:
            return 1
    else:
        return 0

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

#################################################################################################
#                               GRAPH UPDATE FUNCTIONS - BY TWILDER                             #
#################################################################################################

#Entry point for all of the graph analysis. Called by the commander.
def update_graph(instance):
    reset_graph(instance)
    #Updates node information about enemy position, sight, fire
    enemy_belief.update_enemy_graph(instance)
    #Updates graph edges to account for new node information
    update_fire_graph(instance, importance = 10.0)
    update_sight_graph(instance, importance = 1.0)
    update_position_graph(instance, importance = -2.0)
    
def update_visibility_graph(instance):
    #Turn all cells currently seen by enemies to 1 in graph.
    for bot in instance.game.enemyTeam.members:
        if bot.seenlast < 2.0 and bot.health > 0.0:
            cells = one_bot_visibility(instance, bot)
            for cell in cells:
                cell_position = Vector2(cell[0], cell[1])
                index = getNodeIndex(instance, cell_position)
                if can_bot_shoot(instance, bot, cell_position):
                    change_node(instance, index, 1.0)
            for edge in instance.graph.edges():
                #Is the destination of the edge visible to enemies?
                #Set all edges with visible destinations to weight 1.0.
                if instance.graph.node[edge[1]]["weight"] == 1.0:
                    instance.graph.edge[edge[0]][edge[1]]["weight"] = 1.0
                else:
                    instance.graph.edge[edge[0]][edge[1]]["weight"] = .05
                    
def update_fire_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be able to shoot.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy_fire"] + instance.graph.node[end]["p_enemy_fire"]
        instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance

def update_sight_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be able to see.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy_sight"] + instance.graph.node[end]["p_enemy_sight"]
        instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance
                    
def update_position_graph(instance, importance = 1):
    #Weights edges based on where the enemy is likely to be.
    for edge in instance.graph.edges():
        #Edges going through area likely to be shot at are expensive.
        start = edge[0]
        end = edge[1]
        total_density = instance.graph.node[start]["p_enemy"] + instance.graph.node[end]["p_enemy"]
        instance.graph.edge[edge[0]][edge[1]]["weight"] += total_density * importance
        
def reset_graph(instance):
    """0s probability of enemy being at each node."""
    for node_index in instance.graph.nodes():
        instance.graph.node[node_index]["p_enemy"] = 0.0
        instance.graph.node[node_index]["friendly_sight"] = False
        instance.graph.node[node_index]["p_enemy_fire"] = 0.0
        instance.graph.node[node_index]["p_enemy_sight"] = 0.0
        instance.graph.node[node_index]["weight"] = 0
        
    for edge in instance.graph.edges():
        start = edge[0]
        end = edge[1]
        instance.graph.edge[start][end]["weight"] = 0

#################################################################################################
#                UTILITY FUNCTIONS - MOST CODE HERE BY KILLZONE - NOT BY TWILDER                #
#################################################################################################

def calculate_total_enemy_density(instance, nodes):
    total_density = 0.0
    for node_index in nodes:
        total_density += instance.graph.node[node_index]["p_enemy"]
    return total_density

def evaluate_continue_present_command(instance, bot, command):
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
        pass
    
    value = instance.get_hueristic_value(bot, command)
    value += 4 #TODO figure out better way to calculate value of continuing command.
    return value

def enemy_shoots_square(instance, bot, command):
    destination = command.target[0]
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.seenlast < 3.0 and enemy_bot.health > 0.0:
            if can_bot_shoot(instance, enemy_bot, destination):
                return 1
    return 0

def sanitize_position(instance, position):
    #Takes a position we accidentally rounded into that is a block and hence has no node, returns a nearby node that isn't.
    #Since we do this for a lot of points, this is built to only check the height for all but problem points.
    i = int(position.x)
    j = int(position.y)
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
            if count == 10:
                count = 0
                if i > 40:
                    i = i-10
                else:
                    i = i+10
                if j > 25:
                    j = j-10
                else:
                    j = j+10
        position = Vector2(i, j)
    return position 

def get_node_index(instance, position):
    #Ensure we won't accidentally round ourselves into a terrain piece.
    position = sanitize_position(instance, position)
    
    i = int(position.x)
    j = int(position.y)
    #Fixes node 0 bug.
    if i == 0:
        i = 1
    if j == 0:
        j = 1
    width = instance.graph.graph["map_width"]
    #Node bug. #TODO find out real reason for bug instead of hacking solution.
    node_index = i + j*width
    try:
        test = instance.graph.node[node_index]
    except:
        print "NODE BUG"
        print "X: ", i, " Y: ", j, " node: ", node_index
        test = instance.graph.node[node_index]
##    if index in [2905]:# [2905, 2817, 1190, 1185, 4095, 2420]
##        index = i-1 + j*width
    return node_index

def get_node_vector(instance, node_index):
    position = instance.graph.node[node_index]["position"]
    x = position[0]
    y = position[1]
    return Vector2(x , y)

def get_path(instance, start, destination):
    start_node = get_node_index(instance, start)
    destination_node = get_node_index(instance, destination)
    try:
        path = nx.shortest_path(instance.graph, source = start_node, target = destination_node)
    except:
        print "NOT IN GRAPH EXCEPTION"
        print "start: ", start, " start_node: ", start_node
        print "destination: ", destination, " destination_node: ", destination_node
        #Get the exception again.
        path = nx.shortest_path(instance.graph, source = start_node, target = destination_node)
        
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

def can_bot_shoot(instance, bot, position):
    destination_to_bot = bot.position - position
    if can_bot_see(instance, bot, position) and destination_to_bot.length() < instance.level.firingDistance + 1:
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

def change_node(instance, node_index, weight):
    try:
        instance.graph.node[node_index]["weight"] = weight
    except:
        pass
        
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
            print g.nodes()
        #Sets final graph as attribute to the Commander instance.
        instance.graph = g


#################################################################################################
#           GRAPHICS LOGIC - ALL CODE HERE BY KILLZONE - MILDLY REFACTORED BY TWILDER         ###
#################################################################################################

def initialize_graphics(instance):
    from PySide import QtGui, QtCore

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
            visualizer.drawCircle(p, QtGui.qRgb(255,255,0), 5)
            
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

def update_graphics(instance):
    #Set all squares to darkness
    instance.visibilities.fill(0)
    #Set all values to the graph values.
    for node, dictionary in instance.graph.nodes_iter(data=True):
        x = dictionary["position"][0]
        y = dictionary["position"][1]
        weight =  dictionary["weight"]
        instance.visibilities.setPixel(x, y, weight)

def update_graphics_enemy_belief(instance, node_set_list):  
    #Set all squares to darkness
    instance.visibilities.fill(0)
    for node_set in node_set_list:
        for node in node_set:
            x = instance.graph.node[node]["position"][0]
            y = instance.graph.node[node]["position"][1]
            instance.visibilities.setPixel(x, y, random.randrange(0,254))

def update_graphics_friendly_sight(instance):  
    instance.visibilities.fill(0)
    for node in instance.graph.nodes():
        if instance.graph.node[node]["friendly_sight"]:
            x = instance.graph.node[node]["position"][0]
            y = instance.graph.node[node]["position"][1]
            instance.visibilities.setPixel(x, y, 1.0)

#Update graphics based on one of the probabilities on our enemy graph.
def update_graphics_probability(instance, mode = "p_enemy"):  
    instance.visibilities.fill(0)
    for node in instance.graph.nodes():
        x = instance.graph.node[node]["position"][0]
        y = instance.graph.node[node]["position"][1]
        p_mode_true = instance.graph.node[node][mode]
        
        instance.visibilities.setPixel(x, y, p_mode_true * 254)
