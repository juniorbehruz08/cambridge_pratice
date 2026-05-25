from django import template

register = template.Library()


@register.filter
def answer_value(answers, number):
    return answers.get(str(number), '')
