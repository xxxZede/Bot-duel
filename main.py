import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
from datetime import datetime, timedelta
import asyncio
import json
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_CHANNEL_ID = 1304950443704586271
RANK_CHANNEL_ID = 1304948988063252560  # ID du canal pour les classements

# Nom du fichier JSON
FICHIER_JSON = 'save.json'

players_data = {}

# Stockage des données (datetime est transformé en STR en format isoformat)
def enregistrer_donnees(donnees):
    donnees_a_enregistrer = donnees
    for player_id, data in donnees_a_enregistrer.items():
        if isinstance(data['last_assiduite_reset'], datetime):
            data['last_assiduite_reset'] = data['last_assiduite_reset'].isoformat()
    """Enregistre les données dans un fichier JSON."""
    with open(FICHIER_JSON, 'w') as fichier:
        json.dump(donnees_a_enregistrer, fichier, indent=4, ensure_ascii=False)
    print("Données enregistrées avec succès.")

def lire_donnees():
    """Lit et retourne les données depuis le fichier JSON, ou retourne une liste vide si le fichier n'existe pas."""
    if os.path.exists(FICHIER_JSON):
        with open(FICHIER_JSON, 'r') as fichier:
            donnees = json.load(fichier)
        print("Données récupérées avec succès.")
        return donnees
    else:
        print("Aucune donnée trouvée. Création d'une nouvelle liste.")
        return []

# Créer un nouveau dictionnaire avec player_id comme entier et last_assiduite_reset en datetime
players_data = lire_donnees()
updated_players_data = {}
for player_id, data in players_data.items():
    # Convertit player_id en entier
    int_player_id = int(player_id)
    
    # Convertit last_assiduite_reset en datetime si c'est une chaîne
    if isinstance(data['last_assiduite_reset'], str):
        data['last_assiduite_reset'] = datetime.fromisoformat(data['last_assiduite_reset'])
    
    # Ajoute l'entrée mise à jour au nouveau dictionnaire
    updated_players_data[int_player_id] = data

# Remplace players_data par updated_players_data
players_data = updated_players_data


ADMIN_ROLE_ID = 1305225218620526592  # ID du rôle administrateur

def create_embed(title, description, color, footer=None):
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    return embed

def get_player_rank(total_points):
    if total_points >= 500:
        return "👑 Maître"
    elif total_points >= 400:
        return "💠 Diamant"
    elif total_points >= 300:
        return "💎 Platine"
    elif total_points >= 200:
        return "🥇 Or"
    elif total_points >= 100:
        return "🥈 Argent"
    else:
        return "🥉 Bronze"

def is_admin():
    async def predicate(interaction: discord.Interaction):
        role = discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID)
        if role is None:
            await interaction.response.send_message("Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
            return False
        return True
    return commands.check(predicate)

async def update_ranking():

    # Enregistrer les données
    enregistrer_donnees(players_data)


    global rank_message
    channel = bot.get_channel(RANK_CHANNEL_ID)
    if not channel:
        return

    # Recherchez un message existant s'il n'est pas déjà stocké
    if not rank_message:
        async for message in channel.history(limit=50):  # Limite pour éviter trop de messages parcourus
            if message.author == bot.user and message.embeds and message.embeds[0].title == "Classement des joueurs":
                rank_message = message
                break


    # Trier les joueurs par points totaux
    sorted_players = sorted(
        players_data.items(),
        key=lambda item: item[1]['PV'] + item[1]['PA'] + item[1]['PD'],
        reverse=True
    )

    # Générer le texte du classement
    if sorted_players:
        ranking = ""
        for idx, (player_id, data) in enumerate(sorted_players[:25]):
            total_points = data['PV'] + data['PA'] + data['PD']
            rank = get_player_rank(total_points)

            try:
                user = await bot.fetch_user(player_id)
                ranking += f"{idx + 1}. ({rank}) {user.name} - Total: {total_points} points, {data['PV']} PV, {data['PA']} PA, {data['PD']} PD.\n"
            except discord.NotFound:
                ranking += f"{idx + 1}. ({rank}) Utilisateur supprimé - Total: {total_points} points, {data['PV']} PV, {data['PA']} PA, {data['PD']} PD.\n"
            except Exception as e:
                print(f"Erreur lors de la récupération de l'utilisateur {player_id}: {e}")
                ranking += f"{idx + 1}. ({rank}) Erreur lors de la récupération du joueur - {data['PV']} PV, {data['PA']} PA, {data['PD']} PD.\n"
    else:
        ranking = "Aucun joueur n'a encore participé à des duels."

    embed = create_embed(
        "Classement des joueurs",
        ranking,
        discord.Color.gold(),
        footer="Classement actualisé toutes les minutes."
    )

    # Mise à jour ou création du message de classement
    if rank_message:
        try:
            await rank_message.edit(embed=embed)
        except discord.NotFound:
            rank_message = await channel.send(embed=embed)
    else:
        rank_message = await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}!')
    try:
        synced = await bot.tree.sync()
        asyncio.create_task(update_ranking())
        print(f"Synchronisation de {len(synced)} commande(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="duel", description="Proposer un duel avec un autre joueur")
async def duel(interaction: discord.Interaction, member: discord.Member):
    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("La commande !duel peut uniquement être utilisée dans ce canal.", ephemeral=True)
        return

    # Vérification si le joueur se défie lui-même
    if interaction.user == member:
        embed = discord.Embed(
            title="Erreur !",
            description="Tu ne peux pas te défier toi-même !",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return


    # Initialiser les données des joueurs à 0 s'ils n'ont jamais fait de duel
    if interaction.user.id not in players_data:
        players_data[interaction.user.id] = {'PA': 0, 'PV': 0, 'PD': 0, 'last_opponents': [], 'last_assiduite_reset': datetime.now().isoformat(), 'got_assiduite': 0}
    if member.id not in players_data:
        players_data[member.id] = {'PA': 0, 'PV': 0, 'PD': 0, 'last_opponents': [], 'last_assiduite_reset': datetime.now().isoformat(), 'got_assiduite': 0}

    #////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    # Vérifier si le dernier fight était le mois dernier et donc réinitialiser les adversaires.

    if datetime.fromisoformat(players_data[interaction.user.id]['last_assiduite_reset']).month != datetime.now().month:
        players_data[interaction.user.id]['last_opponents'] = []

    if datetime.fromisoformat(players_data[member.id]['last_assiduite_reset']).month != datetime.now().month:
        players_data[member.id]['last_opponents'] = []

    #////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

    # Calculer les rangs des deux joueurs
    player_data = players_data.get(interaction.user.id)
    opponent_data = players_data.get(member.id)

    player_total = player_data['PV'] + player_data['PA'] + player_data['PD']
    opponent_total = opponent_data['PV'] + opponent_data['PA'] + opponent_data['PD']

    # Vérifier la différence de rang
    rank_difference = abs((player_total//100) - (opponent_total//100))
    if rank_difference > 2:
        embed = discord.Embed(
            title="Duel non autorisé",
            description="Les deux joueurs ont plus de 2 rangs d'écart. Le duel est annulé.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = create_embed(
        "Duel proposé !",
        f"{interaction.user.mention} a proposé un duel à {member.mention} ! Acceptez-vous ce duel ?",
        discord.Color.blue(),
        footer="Cliquez sur les boutons pour répondre."
    )

    accept_button = Button(label="Accepter ✅", style=discord.ButtonStyle.green)
    reject_button = Button(label="Refuser ❌", style=discord.ButtonStyle.red)
    cancel_button = Button(label="Annuler 🔙", style=discord.ButtonStyle.gray)

    async def accept_callback(callbackInteraction):
        if callbackInteraction.user == member:
            await callbackInteraction.response.edit_message(content=f"{member.mention} a accepté le duel !", embed=None, view=None)
            await start_duel(interaction, interaction.user, member)
        else:
            await callbackInteraction.response.send_message("Tu n'as pas été invité à ce duel.", ephemeral=True)

    async def reject_callback(callbackInteraction):
        if callbackInteraction.user == member:
            await callbackInteraction.response.edit_message(content=f"{member.mention} a refusé le duel.", embed=None, view=None)
        else:
            await callbackInteraction.response.send_message("Tu n'as pas été invité à ce duel.", ephemeral=True)

    async def cancel_callback(callbackInteraction):
        # Vérifie si c'est l'initiateur ou un administrateur qui annule le duel
        if callbackInteraction.user == interaction.user or callbackInteraction.user.guild_permissions.administrator:
            embed_annulation = discord.Embed(
                title="Duel annulé",
                description=f"{interaction.user.mention} a annulé le duel.",
                color=discord.Color.red()
            )
            await callbackInteraction.response.edit_message(embed=embed_annulation, view=None)
        else:
            await callbackInteraction.response.send_message("Seul l'initiateur du duel ou un administrateur peut annuler le duel.", ephemeral=True)

    # Ajouter les callbacks aux boutons
    accept_button.callback = accept_callback
    reject_button.callback = reject_callback
    cancel_button.callback = cancel_callback

    # Ajouter les boutons dans le View
    view = View()
    view.add_item(accept_button)
    view.add_item(reject_button)

    # Ajouter le bouton d'annulation uniquement pour l'initiateur et les admins
    if interaction.user.guild_permissions.administrator or interaction.user == interaction.user:
        view.add_item(cancel_button)

    # Envoi du message initial et obtention de l'objet Message
    await interaction.response.send_message(content=f"{member.mention} a été défié\n", embed=embed, view=view)
    message = await interaction.original_response()

    # Attente pendant 2 H (7200 secondes)
    await asyncio.sleep(7200)

    # Si aucune réponse, annule automatiquement le duel
    embed_annulation = discord.Embed(
        title="⏳ Temps écoulé - Duel annulé",
        description=f"Le duel entre {interaction.user.mention} et {member.mention} a été annulé car aucune réponse n'a été donnée.\n\n"
                    "Merci de lancer un nouveau défi si vous souhaitez dueller à nouveau.",
        color=discord.Color.red()
    )
    embed_annulation.set_footer(text="Duel expiré - Réessayez à tout moment.")

    # Modification du message initial pour annuler le duel
    if message:
        await message.edit(content="Le temps est écoulé. Le duel est annulé.", embed=embed_annulation, view=None)
    else:
        await interaction.followup.send(content="Erreur : le message n'a pas pu être édité.")


@bot.tree.command(name="info", description="Afficher les informations d'un joueur")
async def info(interaction: discord.Interaction, member: discord.Member):
    # Vérifiez si le canal est correct ou si l'utilisateur est administrateur
    if (interaction.channel.id != ALLOWED_CHANNEL_ID) and (not interaction.user.guild_permissions.administrator):
        await interaction.response.send_message("La commande !info peut uniquement être utilisée par un administrateur dans ce canal.")
        return

    # Vérifiez si le joueur est enregistré
    if member.id not in players_data:
        await interaction.response.send_message("Joueur non enregistré.")
        return

    # Trier les joueurs en fonction de leurs points totaux
    sorted_players = sorted(
        players_data.items(),
        key=lambda item: item[1]['PV'] + item[1]['PA'] + item[1]['PD'],
        reverse=True
    )

    # Calculer les points totaux du joueur
    total_points = players_data[member.id]['PV'] + players_data[member.id]['PA'] + players_data[member.id]['PD']
    
    # Trouver la position du joueur dans le classement
    player_rank = next((index for index, (player_id, _) in enumerate(sorted_players) if player_id == member.id), None)
    if player_rank is not None:
        player_rank += 1  # Ajouter 1 pour rendre le classement humainement lisible

    # Créer l'embed avec les informations du joueur et son rang
    embed = create_embed(
        title="Informations du joueur",
        description=f"Informations de {member.mention} ({get_player_rank(total_points)}):\n\n"
                    f" **(Rang #{player_rank})** \n\n"
                    f"- PV : {players_data[member.id]['PV']}\n"
                    f"- PA : {players_data[member.id]['PA']}\n"
                    f"- PD : {players_data[member.id]['PD']}\n",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Cliquez sur les boutons pour répondre.")

    await interaction.response.send_message(embed=embed)



@bot.tree.command(name="add_points", description="[Admin] Ajouter des points à un joueur")
async def add_points(interaction: discord.Interaction, member: discord.Member, points: int, point_type: str):
    # Vérifiez si l'utilisateur a le rôle d'administrateur
    role = discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID)
    if role is None:
        await interaction.response.send_message("Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    # Vérifiez le type de points
    valid_types = ['PA', 'PD', 'PV']
    if point_type not in valid_types:
        await interaction.response.send_message("Type de points invalide. Utilisez 'PA', 'PD' ou 'PV'.")
        return

    # Initialisez les données du joueur si elles n'existent pas
    if member.id not in players_data:
        players_data[member.id] = {'PA': 0, 'PV': 0, 'PD': 0, 'last_opponents': [], 'last_assiduite_reset': datetime.utcnow().isoformat(), 'got_assiduite': 0}
    
    # Ajouter les points
    players_data[member.id][point_type] += points
    await interaction.response.send_message(f"{member.mention} a reçu {points} points de {point_type}. Total {point_type} : {players_data[member.id][point_type]}.")
    
    # Lancer la mise à jour du classement si nécessaire
    asyncio.create_task(update_ranking())



@bot.tree.command(name="remove_points", description="[Admin] Retirer des points à un joueur")
async def remove_points(interaction: discord.Interaction, member: discord.Member, points: int, point_type: str):
    role = discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID)
    if role is None:
        await interaction.response.send_message("Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    # Vérifiez le type de points
    valid_types = ['PA', 'PD', 'PV']
    if point_type not in valid_types:
        await interaction.response.send_message("Type de points invalide. Utilisez 'PA', 'PD' ou 'PV'.")
        return

    # Initialisez les données du joueur si elles n'existent pas
    if member.id not in players_data:
        players_data[member.id] = {'PA': 0, 'PV': 0, 'PD': 0, 'last_opponents': [], 'last_assiduite_reset': datetime.utcnow().isoformat(), 'got_assiduite': 0}
    
    # Ajouter les points
    players_data[member.id][point_type] -= points
    await interaction.response.send_message(f"{member.mention} a perdu {points} points de {point_type}. Total {point_type} : {players_data[member.id][point_type]}.")
    
    # Lancer la mise à jour du classement si nécessaire
    asyncio.create_task(update_ranking())

@bot.tree.command(name="delete_player", description="[Admin] Supprimmer un joueur de la base de données")
async def delete_player(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID)
    if role is None:
        await interaction.response.send_message("Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        return
    if member.id in players_data:
        del players_data[member.id]
        await interaction.response.send_message(f"{member.mention} a été supprimé du classement.")
    else:
        await interaction.response.send_message(f"{member.mention} n'est pas dans le classement.")
    asyncio.create_task(update_ranking())


import asyncio

async def start_duel(interaction, player1, player2):
    embed = create_embed(
        "Le Duel commence !",
        f"{player1.mention} et {player2.mention}, qui a gagné, qui a perdu ?",
        discord.Color.green(),
        footer="Faites un choix en cliquant sur un bouton."
    )

    win_button = Button(label="Gagner 🏆", style=discord.ButtonStyle.green)
    lose_button = Button(label="Perdre 💔", style=discord.ButtonStyle.red)

    players_choices = {player1.id: None, player2.id: None}
    duel_active = True  # On garde l'état du duel
    lock = asyncio.Lock()  # Verrou pour empêcher les interactions simultanées

    # Fonction pour traiter les choix d'un joueur
    async def process_choice(interaction, choice):
        nonlocal duel_active  # On accède à l'état du duel
        async with lock:  # Verrouille l'accès aux choix
            if players_choices[interaction.user.id] is None:  # Vérifie si le joueur n'a pas encore choisi
                players_choices[interaction.user.id] = choice
                await interaction.response.send_message(f"{interaction.user.mention} a choisi {choice}.", ephemeral=True)

                # Vérifier si tous les joueurs ont fait leur choix
                if None not in players_choices.values():
                    await check_for_winner(interaction, player1, player2, players_choices, interaction.message)
                    duel_active = False  # Le duel est terminé, on bloque plus d'interactions
            else:
                await interaction.response.send_message("Tu as déjà fait ton choix !", ephemeral=True)

    # Callback pour le bouton "Gagner"
    async def win_callback(interaction):
        if duel_active:
            await process_choice(interaction, 'Gagner')

    # Callback pour le bouton "Perdre"
    async def lose_callback(interaction):
        if duel_active:
            await process_choice(interaction, 'Perdre')

    # Créer une vue avec les boutons
    win_button.callback = win_callback
    lose_button.callback = lose_callback

    view = View()
    view.add_item(win_button)
    view.add_item(lose_button)

    # Envoi du message initial du duel
    await interaction.followup.send(embed=embed, view=view)

    # Cette boucle empêche tout clic pendant que le duel est en cours
    while duel_active:
        await asyncio.sleep(1)  # On peut mettre un petit délai pour éviter une boucle trop rapide

    # Après que le duel est terminé, on réactive les boutons pour laisser l'interface se mettre à jour
    await asyncio.sleep(1)  # Attendre 1 seconde avant de réactiver les boutons (si nécessaire)
    view.clear_items()  # Supprime tous les boutons après la fin du duel


async def check_for_winner(ctx, player1, player2, players_choices, duel_message):
    for player in [player1, player2]:
        if player.id not in players_data:
            players_data[player.id] = {
                'PA': 0, 'PV': 0, 'PD': 0,
                'last_opponents': [], 'last_assiduite_reset': datetime.now(), 'got_assiduite': 0
            }

    # Annulation du duel si les choix sont les mêmes
    if players_choices[player1.id] == players_choices[player2.id]:
        embed = create_embed(
            "Duel annulé !",
            f"{player1.mention} et {player2.mention} ont fait le même choix ! Le duel est annulé.",
            discord.Color.red(),
            footer="Recommencez le duel."
        )
        await duel_message.edit(embed=embed, view=None)
        return

    # Identification du gagnant et du perdant
    winner, loser = (player1, player2) if players_choices[player1.id] == 'Gagner' else (player2, player1)

    # Points ajoutés pour le gagnant et le perdant
    winner_pv_gain = 2
    pa_gain = 1
    pd_gain = 1 
    pd_aGagne = 0

    players_data[winner.id]['PV'] += winner_pv_gain
    
        # Avant le duel, on vérifie si le joueur peut encore gagner un PA
    pa_gain_message_winner = "+1" if players_data[winner.id]['got_assiduite'] < 2 else "+0"
    pa_gain_message_loser = "+1" if players_data[loser.id]['got_assiduite'] < 2 else "+0"

    
    for player in [player1, player2]:
        if players_data[player.id]['got_assiduite'] >= 2:
            if player == winner:
                pa_gain_message_winner = "+0"
            else:
                pa_gain_message_loser = "+0"
            # Vérification si une semaine s'est écoulée depuis la dernière réinitialisation
            last_reset = players_data[player.id]['last_assiduite_reset']
            if isinstance(last_reset, str):
                last_reset = datetime.fromisoformat(last_reset) 

            if last_reset is not None:
                # Vérification si une semaine s'est écoulée depuis la dernière réinitialisation
                if datetime.now() - last_reset >= timedelta(weeks=1):
                    # Réinitialisation du compteur got_assiduite
                    players_data[player.id]['got_assiduite'] = pa_gain
                    players_data[player.id]['last_assiduite_reset'] = datetime.now()
                    players_data[player.id]['PA'] += pa_gain
                    if player == winner:
                        pa_gain_message_winner = "+1"
                    else:
                        pa_gain_message_loser = "+1"
        else:
            players_data[player.id]['got_assiduite'] += pa_gain
            players_data[player.id]['PA'] += pa_gain

    if player2.id not in players_data[player1.id]['last_opponents']:
        players_data[player1.id]['PD'] += pd_gain
        pd_aGagne = pd_gain
    if player1.id not in players_data[player2.id]['last_opponents']:
        players_data[player2.id]['PD'] += pd_gain
        pd_aGagne = pd_gain

    # Ajout de chaque joueur dans la liste des derniers adversaires
    if player2.id not in players_data[player1.id]['last_opponents']:
        players_data[player1.id]['last_opponents'].append(player2.id)

    if player1.id not in players_data[player2.id]['last_opponents']:
        players_data[player2.id]['last_opponents'].append(player1.id)

    # Calcul de la perte de PV pour le perdant en fonction de son rang
    loser_total_points = players_data[loser.id]['PV'] + players_data[loser.id]['PA'] + players_data[loser.id]['PD']
    loser_rank = get_player_rank(loser_total_points)

###########################
###########################  Perte de points
###########################

    # Définir la perte de PV en fonction du rang
    if loser_rank == "👑 Maître":
        loser_pv_loss = 0
    elif loser_rank == "💠 Diamant":
        loser_pv_loss = 0
    elif loser_rank == "💎 Platine":
        loser_pv_loss = 0
    elif loser_rank == "🥇 Or":
        loser_pv_loss = 0
    elif loser_rank == "🥈 Argent":
        loser_pv_loss = 0
    else:  # Bronze
        loser_pv_loss = 0

    # perte PV au perdant
    players_data[loser.id]['PV'] = max(0, players_data[loser.id]['PV'] - loser_pv_loss)  # Empêcher que les PV deviennent négatifs

    #rangs actuels
    winner_rank = get_player_rank(players_data[winner.id]['PV'] + players_data[winner.id]['PA'] + players_data[winner.id]['PD'])
    loser_rank = get_player_rank(players_data[loser.id]['PV'] + players_data[loser.id]['PA'] + players_data[loser.id]['PD'])
    #résultat

    # Embed avec l'affichage du gain de PA
    embed = create_embed(
        "Duel terminé !",
        f"{winner.mention} a gagné !\n\n"
        f"**{winner.mention}** ({winner_rank}):\n"
        f"- PV : {players_data[winner.id]['PV']} (+{winner_pv_gain})\n"
        f"- PA : {players_data[winner.id]['PA']} ({pa_gain_message_winner})\n"
        f"- PD : {players_data[winner.id]['PD']} (+{pd_aGagne})\n\n"
        f"**{loser.mention}** ({loser_rank}):\n"
        f"- PV : {players_data[loser.id]['PV']} (-{loser_pv_loss})\n"
        f"- PA : {players_data[loser.id]['PA']} ({pa_gain_message_loser})\n"
        f"- PD : {players_data[loser.id]['PD']} (+{pd_aGagne})\n",
        discord.Color.green()
    )
    await duel_message.edit(embed=embed, view=None)
    asyncio.create_task(update_ranking())
rank_message = None

        
bot.run('MTMwNDkwMDg1NTY1MjI5MDcxMw.G1Wvy1.yKUhDUlz__f3TcD1E1Hs1mHtXl7zbPXh0AdhMM')
