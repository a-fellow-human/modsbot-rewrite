import ast
import asyncio
import logging
import math
import pickle
from datetime import datetime
import datetime as dt
import matplotlib.pyplot as plt
import discord
import schedule
from discord.ext import commands, flags
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

today_messages = {}


class Activity(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('cogs.activity')
        self.new_message = False
        schedule.every().day.at("09:30").do(asyncio.run_coroutine_threadsafe, self.process_today(), bot.loop).tag(
            'cogs.activity')
        schedule.every(5).minutes.do(self.f_dump).tag('cogs.activity')

        # Start
        try:
            x = pickle.load(open('data/activity_dump.p', 'rb'))
            for i in x: today_messages[i] = x[i]
        except FileNotFoundError:
            today_messages.clear()

    async def process_today(self):
        today_date = datetime.now().strftime("%d %b %Y")
        self.logger.info(today_messages)

        # Figure out which users were active today.
        active_users_today = str(today_messages)

        await self.bot.get_channel(cfg.Config.config['log_channel']).send(
            "Logged active users for {}: ```{}```".format(today_date, active_users_today))

        # Log that information.
        r_body = {'values': [[today_date, str(active_users_today)]]}
        cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['activity_sheet'],
                                                          range='Log!A1', valueInputOption='RAW',
                                                          insertDataOption='INSERT_ROWS', body=r_body).execute()

        '''
        # Get the values of the previous x days.
        activity = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                                  range='Log!A2:B').execute().get('values', [])
        active_days = {}
        for i in range(-1, -cfg.Config.config['period_length'] - 1, -1):
            activity_that_day = ast.literal_eval(activity[i][1])
            for user in activity_that_day:
                active_days = active_days.get(user, 0) + 1

        active_users = set()
        for user in active_days:
            if active_days[user] >= cfg.Config.config['days_active_threshold']:
                active_days.add(user)

        for user in active_users:
        '''
        # Clear today's
        today_messages.clear()
        self.f_dump()

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot and message.guild is not None:  # Ignore messages from bots and DMs
            if message.author.id in today_messages:
                today_messages[message.author.id] += 1
            else:
                today_messages[message.author.id] = 1
            cursor = cfg.db.cursor()
            cursor.execute(
                'INSERT INTO messages (discord_message_id, discord_channel_id, discord_user_id, message_length, message_date) VALUES (%s, %s, %s, %s, %s)',
                (message.id, message.channel.id, message.author.id, len(message.content), datetime.now()))
            cfg.db.commit()
        self.new_message = True

    @commands.command()
    @commands.is_owner()
    async def dump_activity(self, ctx):
        await ctx.send(today_messages)

    @commands.command()
    @commands.is_owner()
    async def add_activity(self, ctx, *, activity):
        try:
            activity_dict = ast.literal_eval(activity)
            for user in activity_dict:
                if user in today_messages:
                    today_messages[user] += activity_dict[user]
                else:
                    today_messages[user] = activity_dict[user]
            await ctx.send('Done!: New activity: ```{}```'.format(today_messages))
        except:
            await ctx.send("Something went wrong! ")

    @commands.command()
    @commands.is_owner()
    async def f_dump_activity(self, ctx):
        pickle.dump(today_messages, open('data/activity_dump.p', 'wb+'))
        await ctx.send("Dumped")

    def f_dump(self):
        if self.new_message:
            pickle.dump(today_messages, open('data/activity_dump.p', 'wb+'))
            self.logger.info('Dumped activity: {}'.format(str(today_messages)))
        else:
            self.logger.info('No new messages. ')
        self.new_message = False

    @commands.command()
    @commands.is_owner()
    async def f_load_activity(self, ctx):
        x = pickle.load(open('data/activity_dump.p', 'rb'))
        today_messages.clear()
        for i in x:
            today_messages[i] = x[i]
        await ctx.send("Loaded: ```{}```".format(today_messages))

    @commands.command(aliases=['ad'])
    async def active_days(self, ctx, other: discord.User = None):
        check_id = ctx.author.id if other is None else other.id
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT date(message_date) as date, COUNT(*) AS number
            FROM messages
            WHERE date(message_date) > date_sub(curdate(), interval 14 day) 
            and discord_channel_id != 537818427675377677
            and discord_user_id = {check_id}
            GROUP BY discord_user_id, DATE(message_date)
            HAVING number >= 10
            ORDER BY DATE(message_date), discord_user_id;''')

        days = cursor.fetchall()
        l = len(days)
        if l == 0:
            person = 'You' if other is None else other.display_name
            having = 'have' if other is None else 'has'
            await ctx.author.send(f'{person} {having} 0 active days!')
        else:
            day_info = '\n'.join(f'{a[0]}: {a[1]}' for a in days)
            person = 'You' if other is None else other.display_name
            having = 'have' if other is None else 'has'
            plural = 's' if l > 1 else ''
            await ctx.author.send(f'{person} {having} {l} active day{plural}!  ```Date        Count\n{day_info}\n'
                                  f'[Showing days only where Count >= 10. Messages in bot-spam are not counted.]```')

    @commands.command(aliases=['ua'])
    @commands.check(cfg.is_staff)
    async def update_actives(self, ctx, threshold: int = 7):
        query = '''SELECT discord_user_id as userid, date(message_date) as date, COUNT(*) AS number
        FROM messages
        WHERE date(message_date) > date_sub(curdate(), interval 14 day) and discord_channel_id != 537818427675377677
        GROUP BY discord_user_id, DATE(message_date)
        HAVING number >= 10
        ORDER BY DATE(message_date), discord_user_id;'''

        cursor = cfg.db.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        activity = {}
        for i in rows:
            if i[0] in activity:
                activity[i[0]] += 1
            else:
                activity[i[0]] = 1

        actives_today = set([i for i in activity if activity[i] >= threshold])
        print([i for i in activity if activity[i] >= threshold])
        print(len([i for i in activity if activity[i] >= threshold]))

        active_role = ctx.guild.get_role(cfg.Config.config['active_role'])
        continued_actives = set()
        removed_actives = set()
        new_actives = set()
        for member in active_role.members:
            if member.id in actives_today:
                continued_actives.add(member.id)
            else:
                try:
                    await member.remove_roles(active_role)
                except:
                    pass
                removed_actives.add(member.id)

        for id in actives_today:
            if id not in continued_actives:
                try:
                    await ctx.guild.get_member(id).add_roles(active_role)
                except:
                    pass
                new_actives.add(id)

        ca = ', '.join([str(x) for x in continued_actives]) if len(continued_actives) > 0 else 'None'
        ra = ', '.join([str(x) for x in removed_actives]) if len(removed_actives) > 0 else 'None'
        na = ', '.join([str(x) for x in new_actives]) if len(new_actives) > 0 else 'None'
        print(f'Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```')
        await ctx.guild.get_channel(cfg.Config.config['log_channel']).send(
            f'Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```')

    @flags.add_flag('--interval', type=int, default=30)
    @flags.add_flag('--users', type=int, default=15)
    @flags.command(aliases=['acttop'])
    @commands.cooldown(1, 10, BucketType.user)
    async def activity_top(self, ctx, **flags):
        interval = flags['interval'] if flags['interval'] < 30 else 30
        users = flags['users'] if flags['users'] < 30 else 30
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id, message_date, message_length 
        FROM messages
        WHERE message_date > date_sub(curdate(), interval {interval} day) LIMIT 100000;''')
        messages = cursor.fetchall()
        tss = [(x[0], x[1].timestamp(), x[2]) for x in messages]
        last_message = {}
        score = {}

        def sigmoid(x):
            return 1 / (1 + math.exp(-x))

        def weight(chars, m_date, last_m, now_ts):
            if last_m is None:
                interval = 100
            else:
                interval = (m_date - last_m)
            interval = abs(interval)
            chars = chars if not chars == 0 else 1
            # print(interval)
            try:
                x = math.log10(chars) * sigmoid(6 * interval) * math.exp(
                    (m_date - now_ts) * math.log(0.8, math.e) / 86400)
                # print(x)
                return 10 * math.log10(chars) * sigmoid(6 * interval) * math.exp(
                    (now_ts - m_date) * math.log(0.8, math.e) / 86400)
            except Exception:
                print(chars, interval, m_date, last_m, now_ts)

        now = datetime.now().timestamp()
        for message in tss:
            if message[0] in score:
                score[message[0]] += weight(message[2], message[1], last_message[message[0]], now)
                last_message[message[0]] = message[1]
            else:
                score[message[0]] = weight(message[2], message[1], None, now)
                last_message[message[0]] = message[1]

        scores = [(x, int(score[x])) for x in score]
        scores.sort(key=lambda x: -x[1])
        embed = discord.Embed()
        embed.add_field(name=f'Top 15 users by activity score ({interval} day)',
                        value='\n'.join([f'`{i+1}.` <@!{scores[i][0]}>: `{scores[i][1]}`' for i in range(users)]))
        await ctx.send(embed=embed)


@flags.add_flag('--interval', type=int, default=None)
@flags.add_flag('--user', type=discord.User, default=None)
@commands.cooldown(1, 10, BucketType.user)
@flags.command()
async def activity(ctx, **flags):
    messages = []
    ticks = []
    delta = dt.timedelta(days=1)
    index = 0
    end = datetime.now().date()
    interval = flags['interval']
    user = flags['user']

    if interval is None:
        interval = (end - (dt.date(2020, 7, 1))) / delta
    if interval > (end - dt.date(2020, 7, 1)) / delta:
        await ctx.send(f'Too big interval (max size: `{(end - (dt.date(2020, 7, 1))) // delta}`)')
        return

    if user is None:
        user = ctx.author

    cursor = cfg.db.cursor()
    cursor.execute(f'''
    SELECT date(message_date) as date, COUNT(*) AS number
    FROM messages
    WHERE date(message_date) > date_sub(curdate(), interval {interval} day) 
    and discord_user_id = {user.id}
    GROUP BY discord_user_id, DATE(message_date)
    ORDER BY DATE(message_date), discord_user_id;
    ''')
    result = cursor.fetchall()

    plt.style.use('ggplot')

    start = end - (interval - 1) * delta
    while start <= end:
        if len(result) > index and result[index][0] == start:
            messages.append(result[index][1])
            index += 1
        else:
            messages.append(0)
        ticks.append(start if start.weekday() == 0 else None)
        start += delta
    x_pos = [i for i, _ in enumerate(messages)]
    print(x_pos)
    print(messages)
    plt.bar(x_pos, messages, color='green')
    plt.xlabel("Date")
    plt.ylabel("Messages")
    plt.title(f"{user.display_name}'s Activity")
    plt.axhline(y=10, linewidth=1, color='r')

    plt.xticks(x_pos, ticks)
    fname = f'data/{datetime.now().isoformat()}.png'
    plt.savefig(fname)
    await ctx.send(file=discord.File(open(fname, 'rb')))
    plt.clf()


def setup(bot):
    bot.add_cog(Activity(bot))
    bot.add_command(activity)
